"""Story gate — conditions for a story to be considered done.

The gate reads **evidence**, not agent claims. Every agent ends with
"completed"; that sentence carries no information. What carries information
is: whether a test run exists, green or red, run before or after the last
edit, whether the git tree stays within scope, whether the real screen has
all promised components.

Nine conditions, each answerable from available data:

1. tests green, and green **after** the last file edit;
2. lint clean;
3. changes within ``write_scope``;
4. screen matches visual contract (UI stories only);
5. independent review has no blocking items;
6. no fake tests — tests asserting nothing make condition 1 vacuous;
7. preservation (ADR-004 R4) — VERIFIED behaviours of other stories whose
   files this story touches are still green at the candidate; unverifiable
   is reported as unverifiable, not as passed.
8. no baseline regression — tests green at baseline (before the story
   touched anything) must remain green and present at candidate (ADR-004 R9).
9. tests verify story (nop control, ADR-005 V3) — tests carrying criteria
   codes must be **red without the story's code**: not already green at
   baseline (level 1, $0) and red or absent at parent SHA with test files
   copied in (level 2, one sandbox run). Green at both places is a label,
   not a verification.

The **closed** list of check names is `CHECK_NAMES`; each check has `kind`
(who scores it — `CHECK_KIND`) and `evidence` (seq of events read); each
name has three controls in `tests/test_gate_qualification.py`, table read
by `qualification_table()` (ADR-005 V9).
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

from ..harness.guardrails import check_completion, check_diff_scope
from .acceptance import ac_code, coverage as ac_coverage, missing as ac_missing
from .outcome import Check, Outcome
from .tdd import red_before_green
from .security import DEFAULT_BLOCKING
from ..harness.observe import FILE_CHANGE, GUARD_BLOCK, GUARD_SEEN, MOCKUP_MAP, NOTE, TOOL_RUN, Event, Evidence
from ..harness.testlog import MAX_IDS
from ..harness.tools import BASELINE_RUN, NOP_RUN

#: Story gate check names — **closed** list (ADR-005 V9). Every `Check(...)` in
#: this file must use a name from here (test meta grep AST), and each name has
#: three controls positive / negative / env in `tests/test_gate_qualification.py`.
#: `<kind>` is the check **family** per verification contract: the actual check
#: name is the kind (`e2e`, `accessibility`, `perf`... — `phases/qa.py::KINDS`
#: minus unit/mockup-map/security which have dedicated checks).
CHECK_NAMES = (
    "evidence matches candidate",
    "guard ran",
    "test",
    "no baseline regression",
    "lint",
    "write scope",
    "mockup map",
    "real tests",
    "criteria have tests",
    "coverage",
    "TDD",
    "tests verify story",
    "<kind>",
    "security",
    "review",
    "preservation",
)

#: Who scores each check — single source, values from `outcome.CHECK_KINDS`.
#: Deterministic machine reads runner results; structural machine compares
#: file scope, test names, DOM, guard traces, SHA; security review; model as
#: judge. No check is `human` yet.
CHECK_KIND = {
    "evidence matches candidate": "structural",
    "guard ran": "structural",
    "test": "deterministic",
    "no baseline regression": "deterministic",
    "lint": "deterministic",
    "write scope": "structural",
    "mockup map": "structural",
    "real tests": "structural",
    "criteria have tests": "structural",
    "coverage": "deterministic",
    "TDD": "deterministic",
    "tests verify story": "deterministic",
    "<kind>": "deterministic",
    "security": "security",
    "review": "model-judge",
    "preservation": "deterministic",
}

#: Three controls certifying a check (Inspect `tests/scorer/*`, TB oracle/nop):
#: positive (good evidence -> PASSED/NOT_APPLICABLE with name), negative/mutant
#: (bad evidence -> FAILED, or blocks when the check design has no FAILED), env
#: (environment/config prevents conclusion -> named outcome, not a pass).
CONTROLS = ("positive", "negative", "env")

#: Record of `--verify-only --repeat k` (ADR-004 R13): which checks changed
#: outcome across k runs on the same SHA. Written by `implement._repeat_note`.
REPEAT_NOTE = "verify-only.repeat"


@dataclass
class StoryGate:
    story_id: str
    checks: list[Check] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not any(c.outcome.blocks for c in self.checks)

    @property
    def failures(self) -> list[Check]:
        return [c for c in self.checks if c.outcome.blocks]

    def summary(self) -> str:
        head = f"story gate {self.story_id}: {'PASS' if self.passed else 'FAIL'}"
        return "\n".join([head, *(c.line() for c in self.checks)])

    def feedback(self) -> str:
        """Feedback to pass back to the agent on the next attempt."""
        return "\n".join(f"- {c.name}: {c.detail}" for c in self.failures)


def _stale_candidates(evidence: Evidence, candidate: str) -> list[str]:
    """Old candidates that the **latest result** of a check still refers to.

    Compared per check (kind + name), not per evidence file: the previous
    attempt leaving results at the old candidate is normal — rerunning on
    the new candidate is sufficient. What is abnormal is when the **latest**
    check still belongs to a different candidate: code changed after testing.
    """
    return sorted({str(e.detail["candidate"]) for e in _latest_per_check(evidence).values()
                   if str(e.detail["candidate"]) != candidate})


def _latest_per_check(evidence: Evidence) -> dict[tuple[str, str], Event]:
    """**Latest** result of each check (kind + name) that declares a candidate —
    exactly the events the "evidence matches candidate" check reads, so its
    `evidence` field points here."""
    moi_nhat: dict[tuple[str, str], Event] = {}
    for e in evidence.events:
        if e.kind in (TOOL_RUN, MOCKUP_MAP) and e.detail.get("candidate"):
            moi_nhat[(e.kind, e.name)] = e
    return moi_nhat


def _ten(tests: list[str], n: int = 5) -> str:
    return ", ".join(tests[:n]) + (f" (+{len(tests) - n})" if len(tests) > n else "")


def _flaky_ids(evidence: Evidence) -> list[str]:
    """Test names that changed outcome across k runs on the same SHA (`--repeat k`)."""
    note = evidence.last(NOTE, REPEAT_NOTE)
    return [str(t) for t in (note.detail.get("flaky_ids") or [])] if note else []


def _khong_on_dinh(evidence: Evidence, name: str) -> str:
    """Flakiness reason for check ``name`` from the `--repeat k` record; empty
    if nothing to report.

    Code unchanged across k runs but outcome changes means it is not red
    (nothing to fix in code) and not a pass (cannot run stably) -> UNRUNNABLE,
    naming the tests — bug 22: `autosave.spec.ts:210` was load-sensitive,
    causing e9 STORY-01-07 to fail attempt 3 then go 10/10 green on retest.
    Red on **every** run (`stable_red`) is a real failure: not classified
    here, last run is red and the "test" check scores FAILED as usual.
    Checks that don't print test names (lint, `qa:<kind>`) compare the whole
    check: `ok` changing across runs means flaky.
    """
    note = evidence.last(NOTE, REPEAT_NOTE)
    if note is None:
        return ""
    d = note.detail
    if name == "test" and d.get("stable_red"):
        return ""
    lat = _flaky_ids(evidence) if name == "test" else []
    if not lat and name not in (d.get("flaky_checks") or []):
        return ""
    return (
        f"flaky across {d.get('k')} runs on the same SHA"
        + (f": {_ten(lat)}" if lat else "")
        + " — unstable results are neither a failure nor a pass"
    )


def _la(test_id: str) -> str:
    """Leaf title of a test id: part after the last `>`, stripping leading `AC_...:` code."""
    la = test_id.rsplit(">", 1)[-1].strip()
    if ":" in la and la.split(":", 1)[0].replace("_", "-").upper().startswith("AC-"):
        la = la.split(":", 1)[1].strip()
    return la


def _baseline_check(evidence: Evidence, candidate: str) -> Check:
    """Check "no baseline regression" (ADR-004 R9).

    The "test" check only says whether the last run is green or red. Red from
    a **new** test (TDD, legitimately red) and red from a **pre-existing**
    test just broken look identical there — but the fix differs, and the
    latter is a regression that must be named. So compare two name lists:
    tests green at baseline (harness runs before the developer session,
    `test:baseline`) with the latest test run at the candidate. Green before
    but red or missing after -> regression, named. Tests already red at
    baseline are excluded — stated explicitly.

    Outcomes follow the invariant: no baseline because **test command not
    configured** or reporter **doesn't print names** -> UNCONFIGURED (not a
    pass, not blocking, must be visible); baseline **unrunnable** (tool not
    installed) -> UNRUNNABLE (blocks with environment reason, not "story
    broke it"); disabled by `verify.baseline` or harness recorded no baseline
    -> NOT_APPLICABLE with reason. Tests **gone** is regression: deleting or
    renaming existing tests must be declared in the story, and the story has
    no place to declare that yet — cannot infer intent, so not allowed, with
    clear explanation.
    """
    ten = "no baseline regression"
    goc = evidence.last(TOOL_RUN, BASELINE_RUN)
    if goc is None:
        return Check(ten, Outcome.NOT_APPLICABLE,
                     "harness recorded no baseline (manual run, old journal) — cannot compare")
    doc = [goc.seq]     # events read: baseline, then test run at candidate
    if goc.detail.get("disabled"):
        return Check(ten, Outcome.NOT_APPLICABLE, "disabled by `verify.baseline` config", evidence=doc)
    if goc.detail.get("skipped"):
        return Check(ten, Outcome.UNCONFIGURED, f"no baseline: {goc.detail['skipped']}", evidence=doc)
    if goc.detail.get("unrunnable"):
        return Check(ten, Outcome.UNRUNNABLE,
                     f"baseline unrunnable ({goc.detail['unrunnable']}) — cannot compare existing tests",
                     evidence=doc)
    if not goc.detail.get("test_format"):
        return Check(ten, Outcome.UNCONFIGURED, str(goc.detail.get("test_note") or "")
                     or "cannot read test names from baseline — use a reporter that prints names "
                        "(`node --test`, `vitest --reporter=verbose`, `pytest -v`, CTRF)",
                     evidence=doc)

    # Test run at candidate: after baseline, and matching the candidate being
    # scored (when candidate is given, reject manual runs without a candidate).
    sau = [e for e in evidence.of(TOOL_RUN, "test")
           if e.seq > goc.seq and (not candidate or e.detail.get("candidate") == candidate)]
    if not sau:
        return Check(ten, False, "no test run at candidate after baseline — cannot compare",
                     evidence=doc)
    moi = sau[-1]
    doc.append(moi.seq)
    if moi.detail.get("unrunnable"):
        return Check(ten, Outcome.UNRUNNABLE,
                     f"candidate test run unrunnable ({moi.detail['unrunnable']}) — cannot compare",
                     evidence=doc)
    if not moi.detail.get("test_format"):
        return Check(ten, Outcome.UNCONFIGURED, str(moi.detail.get("test_note") or "")
                     or "cannot read test names at candidate — use a reporter that prints names", evidence=doc)

    goc_ids = list(goc.detail.get("test_ids") or [])
    khong_xanh = set(goc.detail.get("failed_ids") or []) | set(goc.detail.get("skipped_ids") or [])
    xanh_goc = [t for t in goc_ids if t not in khong_xanh]
    # `--repeat k`: tests changing outcome across k runs at candidate are not
    # "broke" — the "test" check already records UNRUNNABLE naming them;
    # excluded here, and stated.
    lat = _flaky_ids(evidence)
    do = set(moi.detail.get("failed_ids") or []) - set(lat)
    con = set(moi.detail.get("test_ids") or [])
    lam_do = [t for t in xanh_goc if t in do]
    # ponytail: testlog truncates list at MAX_IDS — test suites larger than
    # that cannot conclude "lost" (name may be beyond the cutoff), only compare red.
    cat = len(goc_ids) >= MAX_IDS or len(con) >= MAX_IDS
    # Rename != lost: same leaf title (part after last `>`) still present at
    # candidate means the test is still there, just under a different group/code
    # name. e9 01-07 attempt 2 (2026-09-06): developer added `AC_STORY_01_01_6:`
    # prefix to four existing tests to close GAPs of another story — gate read
    # it as "lost 4 tests". A real deletion loses the leaf title too, still caught.
    la_con = {_la(t) for t in con}
    doi_ten = [] if cat else [t for t in xanh_goc if t not in con and _la(t) in la_con]
    mat = [] if cat else [t for t in xanh_goc if t not in con and _la(t) not in la_con]
    if lam_do or mat:
        loi = []
        if lam_do:
            loi.append(f"broke {len(lam_do)} tests green at baseline: {_ten(lam_do)}")
        if mat:
            loi.append(f"lost {len(mat)} tests present at baseline: {_ten(mat)} — deleting or renaming "
                       "existing tests must be declared in the story; evidence cannot infer intent "
                       "so this counts as regression")
        return Check(ten, False, "; ".join(loi), evidence=doc)
    do_san = list(goc.detail.get("red_before") or goc.detail.get("failed_ids") or [])
    if doi_ten:
        return Check(ten, True, f"{len(doi_ten)} tests renamed but leaf title still present, not counted as lost: {_ten(doi_ten)}",
                     evidence=doc)
    if do_san:
        return Check(ten, True, f"{len(do_san)} tests already red at baseline, not counted: {_ten(do_san)}",
                     evidence=doc)
    if lat:
        return Check(ten, True, f"{len(lat)} flaky tests not counted here (see test check): {_ten(lat)}",
                     evidence=doc)
    if cat:
        return Check(ten, True, f"test list truncated at {MAX_IDS} names — can only compare red tests, cannot detect lost tests",
                     evidence=doc)
    return Check(ten, True, evidence=doc)


def _nop_check(evidence: Evidence, story_id: str, *, acceptance: int, candidate: str) -> Check:
    """Check "tests verify story" — nop control (ADR-005 V3).

    The question from Terminal-Bench (nop < 1), BERBench (`base_fail`) and
    Agentless (reproduction test): **without the story's code, the story's
    tests must be red**. `TDD` only asks "was there any red run before the
    last green" — a syntax error red also passes. Here we ask directly at
    two levels, cheapest first:

    **Level 1 ($0, from `test:baseline` R9):** tests carrying `AC-<story>-i`
    green at candidate that were already green at baseline — same name, or old
    name gone but leaf title (`_la`) still present, meaning renamed to carry
    the code — are "tagging existing tests" (bug 23 -> 24: developer tagged
    four existing tests to silence the gate): green **before the story wrote
    a line**, so they verify nothing of the story. No exception for "story
    only edits/renames existing tests" even though the test body may differ:
    $0 evidence only sees names, the criteria code contract is by **name**
    (the *criteria have tests* check), and level 2 — which can see test
    bodies — doesn't always run (`verify.nop` disabled, can't build parent
    SHA). Loosening here lets through exactly the class of bugs V3 was built
    to catch; cheap fix (one attempt): write **new** tests with codes, keep
    existing tests under original names. No false positives: a new test
    sharing a leaf title with an existing test **still present by name** at
    candidate is a different test — left to level 2. Baseline of a retry
    stands at the story's own build (`parent` != `base_ref`, e9 01-07
    attempt 3) so all story tests are already green — level 1 cannot
    compare, stated, level 2 decides (worktree at the correct branch point).

    **Level 2 (`test:nop`, harness runs after freeze):** at the parent SHA
    with story test files copied in, tests carrying codes must be **red or
    absent** — import errors at parent SHA count as red and are valid. Green
    -> FAILED naming the tests. Other outcomes per invariant: nop unrunnable
    -> UNRUNNABLE; reporter doesn't print names (only knows test suite is
    red, not whose) -> UNCONFIGURED; story didn't add/modify test files,
    disabled by `verify.nop`, or harness recorded no nop (journal before V3)
    -> NOT_APPLICABLE with reason.
    """
    ten = "tests verify story"
    goc = evidence.last(TOOL_RUN, BASELINE_RUN)
    sau = [e for e in evidence.of(TOOL_RUN, "test")
           if (goc is None or e.seq > goc.seq)
           and (not candidate or e.detail.get("candidate") == candidate)]
    moi = sau[-1] if sau else None
    nop = evidence.last(TOOL_RUN, NOP_RUN)
    # Event pointers read: baseline, test run at candidate, nop — whichever exist.
    doc = [e.seq for e in (goc, moi, nop) if e is not None]

    def ket(outcome, detail: str = "") -> Check:
        return Check(ten, outcome, detail, evidence=doc)

    # Tests with criteria codes **green** at candidate — subject of both levels.
    ac: list[str] = []
    if moi is not None and moi.detail.get("test_format") and acceptance > 0:
        do = set(moi.detail.get("failed_ids") or []) | set(moi.detail.get("skipped_ids") or [])
        xanh_moi = [t for t in moi.detail.get("test_ids") or [] if t not in do]
        for tests in ac_coverage(story_id, acceptance, xanh_moi).values():
            ac.extend(t for t in tests if t not in ac)

    # ---- level 1
    cap1 = ""
    if ac and goc is not None and goc.detail.get("test_format"):
        re_nhanh, cha = str(goc.detail.get("base_ref") or ""), str(goc.detail.get("parent") or "")
        if re_nhanh and cha and re_nhanh != cha:
            cap1 = (f"level 1 cannot compare: baseline ran at {cha[:7]} — the story's own build "
                    f"(rerun), not the branch point {re_nhanh[:7]}")
        else:
            goc_ids = list(goc.detail.get("test_ids") or [])
            khong_xanh = set(goc.detail.get("failed_ids") or []) | set(goc.detail.get("skipped_ids") or [])
            xanh_goc = {t for t in goc_ids if t not in khong_xanh}
            con = set(moi.detail.get("test_ids") or [])
            gan = [t for t in ac if t in xanh_goc]
            cat = len(goc_ids) >= MAX_IDS or len(con) >= MAX_IDS
            la_mat = set() if cat else {_la(t) for t in xanh_goc if t not in con}
            doi = [t for t in ac if t not in goc_ids and _la(t) in la_mat]
            loi = []
            if gan:
                loi.append(f"tagged existing tests: {len(gan)} tests with criteria codes were already green at "
                           f"baseline under the same name — green before the story wrote a line: {_ten(gan)}")
            if doi:
                loi.append(f"renamed existing tests to carry codes: {len(doi)} tests were green at baseline under "
                           f"their old name — criteria code became a label, not a verification: {_ten(doi)}")
            if loi:
                return ket(False, "; ".join(loi) + ". Write new tests for criteria, keep existing tests under their original names")

    # ---- level 2
    if nop is None:
        return ket(Outcome.NOT_APPLICABLE,
                     "harness ran no nop (manual run, journal before ADR-005 V3) — cannot compare")
    d = nop.detail
    if d.get("disabled"):
        return ket(Outcome.NOT_APPLICABLE, "disabled by `verify.nop` config")
    if d.get("skipped"):
        if "files" in d and not d["files"]:
            return ket(Outcome.NOT_APPLICABLE, "story did not add/modify test files")
        return ket(Outcome.UNCONFIGURED, f"no nop: {d['skipped']}")
    if d.get("unrunnable") and not d.get("test_format"):
        return ket(Outcome.UNRUNNABLE,
                     f"nop at parent SHA unrunnable ({d['unrunnable']}) — cannot compare")
    cha = str(d.get("parent") or "")[:7] or "cha"
    if moi is None:
        return ket(False, "no test run at candidate — cannot determine which tests are green to compare with parent SHA")
    if d.get("test_format") and moi.detail.get("test_format") and acceptance > 0:
        if not ac:
            return ket(False, "no tests with criteria codes green at candidate — nothing "
                                     "to verify at parent SHA (see criteria have tests check)")
        khong = set(d.get("failed_ids") or []) | set(d.get("skipped_ids") or [])
        xanh_nop = {t for t in d.get("test_ids") or [] if t not in khong}
        van_xanh = [t for t in ac if t in xanh_nop]
        if van_xanh:
            return ket(False, f"tests verify nothing — still green without story code "
                                     f"(parent SHA {cha}): {_ten(van_xanh)}")
        return ket(True, f"{len(ac)} tests with criteria codes are red or absent at parent SHA {cha}"
                                + (f"; {cap1}" if cap1 else ""))
    if nop.ok:
        return ket(False, f"test suite green at parent SHA {cha} with story test files copied in — "
                                 f"story tests verify nothing ({_ten(list(d.get('files') or []), 3)})")
    if acceptance <= 0:
        return ket(True, f"test suite red at parent SHA {cha} — story declares no criteria, not compared by code")
    return ket(Outcome.UNCONFIGURED,
                 "cannot read test names — only know test suite is red at parent SHA, cannot tell if those are "
                 "story tests; use a reporter that prints names (`node --test`, `vitest --reporter=verbose`, `pytest -v`)")


def evaluate(
    story_id: str,
    evidence: Evidence,
    *,
    changed: list[str],
    write_scope: list[str],
    screens: list[str],
    contract: list[str] | None = None,
    review_blocking: list[str] | None = None,
    review_ran: bool = True,
    security=None,
    block_severities=None,
    guard_expected: bool = False,
    acceptance: int = 0,
    coverage_min: float | None = None,
    added_tests: list[str] | None = None,
    candidate: str = "",
    preservation: list[dict] | None = None,
) -> StoryGate:
    """Score a story from recorded evidence.

    ``candidate`` is the SHA of the build being scored (ADR-004 R1). When
    given, evidence recorded at a different build **is not used for scoring**,
    and the gate says so instead of silently scoring with stale metrics.
    Empty = no check (manual run, old journal).

    ``preservation`` is VERIFIED behaviours of other stories whose files
    this story touches (ADR-004 R4, `implement.preservation_items`). Empty =
    not applicable, so old callers see no change in outcome.
    """
    gate = StoryGate(story_id=story_id)

    stale = _stale_candidates(evidence, candidate) if candidate else []
    moi_nhat = _latest_per_check(evidence)
    if not candidate:
        gate.checks.append(Check(
            "evidence matches candidate", Outcome.NOT_APPLICABLE,
            "no candidate passed — cannot verify which build evidence belongs to",
        ))
    elif stale:
        gate.checks.append(Check(
            "evidence matches candidate", Outcome.UNRUNNABLE,
            f"stale: recorded at {', '.join(s[:7] for s in stale)}, "
            f"current candidate is {candidate[:7]} — rerun checks on this build",
            evidence=[e.seq for e in moi_nhat.values() if str(e.detail["candidate"]) != candidate],
        ))
    else:
        gate.checks.append(Check("evidence matches candidate", True,
                                 evidence=[e.seq for e in moi_nhat.values()]))
    if candidate:
        # After stating it, drop stale evidence: a check from another build
        # must not silently make any check pass.
        evidence = evidence.for_candidate(candidate)

    # Hook generated != hook running. Claude Code only reads `.claude/settings.json`
    # of the tree it stands in; worktree lacking that directory (project didn't
    # commit it) means the story runs with zero guards — and evidence looks
    # identical to a well-behaved agent, because there is nothing to record.
    # Now guard self-records `GUARD_BLOCK`/`FILE_CHANGE`, so "guard never
    # evaluated a write operation" is measurable.
    if not guard_expected:
        gate.checks.append(Check(
            "guard ran", Outcome.NOT_APPLICABLE,
            "hooks not compiled for this client — not expected",
        ))
    else:
        # First trace is enough to answer "did the hook fire".
        dau_vet = evidence.of(GUARD_SEEN) or evidence.of(GUARD_BLOCK) or evidence.of(FILE_CHANGE)
        gate.checks.append(Check(
            "guard ran", evidence.guard_reached,
            "" if evidence.guard_reached else (
                "guard did not evaluate any write in this session — hook cannot "
                "reach worktree? (.claude/ not committed, or --settings not "
                "passed). A story that writes nothing also lands here, and that is correct."
            ),
            evidence=[dau_vet[0].seq] if dau_vet else [],
        ))

    completion = check_completion(evidence)
    last_test = evidence.last(TOOL_RUN, "test")
    # `completion` reads the last test run and files edited **after** it — point to both.
    doc_test = ([last_test.seq] + [e.seq for e in evidence.of(FILE_CHANGE) if e.seq > last_test.seq]
                if last_test is not None else [])
    lat = _khong_on_dinh(evidence, "test")
    if last_test is not None and last_test.detail.get("unrunnable"):
        gate.checks.append(Check("test", Outcome.UNRUNNABLE, str(last_test.detail["unrunnable"]),
                                 evidence=doc_test))
    elif lat:
        gate.checks.append(Check("test", Outcome.UNRUNNABLE, lat, evidence=doc_test))
    else:
        gate.checks.append(Check("test", completion.allowed, completion.reason.split("\n")[0],
                                 evidence=doc_test))
    gate.checks.append(_baseline_check(evidence, candidate))

    lint = evidence.last(TOOL_RUN, "lint")
    if lint is None:
        gate.checks.append(Check("lint", False, "lint has never been run"))
    elif lint.detail.get("skipped"):
        gate.checks.append(
            Check("lint", Outcome.UNCONFIGURED, str(lint.detail["skipped"]), evidence=[lint.seq])
        )
    elif _khong_on_dinh(evidence, "lint"):
        gate.checks.append(Check("lint", Outcome.UNRUNNABLE, _khong_on_dinh(evidence, "lint"),
                                 evidence=[lint.seq]))
    else:
        gate.checks.append(
            Check("lint", lint.ok, "" if lint.ok else str(lint.detail.get("tail", ""))[:300],
                  evidence=[lint.seq])
        )

    # Inferred from parameters (`changed`, `write_scope` — git tree read by
    # `run_attempt`), not from events: `evidence` is empty, and empty is correct.
    scope = check_diff_scope(changed, write_scope)
    gate.checks.append(Check("write scope", scope.allowed, scope.reason))

    if not screens:
        gate.checks.append(Check("mockup map", Outcome.NOT_APPLICABLE, "story has no UI"))
    else:
        maps = {e.name: e for e in evidence.of(MOCKUP_MAP)}
        doc_map = [maps[s].seq for s in screens if s in maps]
        missing_runs = [s for s in screens if s not in maps]
        if missing_runs:
            gate.checks.append(
                Check("mockup map", False, f"not compared: {', '.join(missing_runs)}", evidence=doc_map)
            )
        else:
            failed = [s for s in screens if not maps[s].ok]
            detail = ""
            if failed:
                first = maps[failed[0]].detail
                detail = (
                    f"{failed[0]} missing: "
                    + ", ".join(first.get("missing", []) + first.get("missing_data_roles", []))
                )
            gate.checks.append(Check("mockup map", not failed, detail, evidence=doc_map))

    fake = evidence.last(TOOL_RUN, "qa:fake-tests")
    if fake is not None and not fake.ok:
        files = fake.detail.get("files") or []
        gate.checks.append(
            Check("real tests", False,
                  f"{len(files)} tests have no assertions: {', '.join(files[:3])}",
                  evidence=[fake.seq])
        )
    else:
        gate.checks.append(Check("real tests", True, evidence=[fake.seq] if fake is not None else []))

    # Criteria have tests (G5): `AC-<story>-<i>` code must appear in the name
    # of a test in the last green run — names read from runner output, not
    # agent claims. Cannot read test names -> **unconfigured** reporter, not
    # a story fault and not a pass.
    xanh = [e for e in evidence.of(TOOL_RUN, "test") if e.ok]
    last_green = xanh[-1] if xanh else None
    doc_xanh = [last_green.seq] if last_green is not None else []
    if acceptance <= 0:
        gate.checks.append(Check("criteria have tests", Outcome.NOT_APPLICABLE, "story declares no criteria"))
    elif last_green is None:
        gate.checks.append(Check("criteria have tests", False, "no green test run yet"))
    elif not last_green.detail.get("test_format"):
        gate.checks.append(Check(
            "criteria have tests", Outcome.UNCONFIGURED,
            str(last_green.detail.get("test_note") or "")
            or "cannot read test names from runner output — use a reporter that prints names "
               "(`node --test`, `vitest --reporter=verbose`, `pytest -v`, CTRF)",
            evidence=doc_xanh,
        ))
    else:
        thieu = ac_missing(story_id, acceptance, list(last_green.detail.get("test_ids") or []))
        gate.checks.append(Check(
            "criteria have tests", not thieu,
            "" if not thieu else
            f"no tests with codes {', '.join(ac_code(story_id, i) for i in thieu)} — "
            f"each criterion needs at least one test named after its code",
            evidence=doc_xanh,
        ))

    # coverage.min (G10b): number read from runner output. No number means
    # runner has not enabled coverage — state the fix, do not count as pass.
    if coverage_min is not None:
        cov = last_green.detail.get("coverage") if last_green else None
        if last_green is None:
            gate.checks.append(Check("coverage", Outcome.UNCONFIGURED, "no green test run to measure"))
        elif cov is None:
            gate.checks.append(Check(
                "coverage", Outcome.UNCONFIGURED,
                "runner did not print coverage — add `--coverage` (vitest/c8) or `--cov` (pytest) to the test command",
                evidence=doc_xanh,
            ))
        else:
            nguong = coverage_min * 100
            gate.checks.append(Check(
                "coverage", float(cov) >= nguong,
                f"{float(cov):.0f}%" if float(cov) >= nguong else f"{float(cov):.0f}% < {nguong:.0f}%",
                evidence=doc_xanh,
            ))

    # TDD (G8): story added tests must have a red run before the last green.
    if added_tests is not None:
        if not added_tests:
            gate.checks.append(Check("TDD", Outcome.NOT_APPLICABLE, "story did not add tests"))
        else:
            gate.checks.append(Check(
                "TDD", red_before_green(evidence),
                "" if red_before_green(evidence) else
                f"tests green on first run — not proven to verify anything "
                f"({', '.join(added_tests[:3])}). Write tests first, see them fail, then write code.",
                evidence=[e.seq for e in evidence.of(TOOL_RUN, "test")],   # red/green order read across full sequence
            ))
    # Nop control (ADR-005 V3) right after TDD: same question, asked directly.
    gate.checks.append(_nop_check(evidence, story_id, acceptance=acceptance, candidate=candidate))

    # Story verification contract. Unconfigured kinds are recorded as
    # **unconfigured**, not passed — they block at the pre-deploy gate, and
    # here they must be visible so the reader knows where the gap is.
    for kind in contract or []:
        if kind in ("unit", "mockup-map", "security"):
            continue  # already has a dedicated check above
        # `run_suite` records `qa:<kind>`; bare name is from manual runs/`aisef tool`.
        # e9 2026-09-05: e2e/perf/accessibility ran and were green but gate said
        # "unconfigured" because it only looked for bare names.
        ran = evidence.last(TOOL_RUN, f"qa:{kind}") or evidence.last(TOOL_RUN, kind)
        if ran is None:
            gate.checks.append(Check(kind, Outcome.UNCONFIGURED, kind=CHECK_KIND["<kind>"]))
        elif ran.detail.get("skipped"):
            gate.checks.append(Check(kind, Outcome.UNCONFIGURED, str(ran.detail["skipped"]),
                                     kind=CHECK_KIND["<kind>"], evidence=[ran.seq]))
        elif _khong_on_dinh(evidence, f"qa:{kind}"):
            gate.checks.append(Check(kind, Outcome.UNRUNNABLE, _khong_on_dinh(evidence, f"qa:{kind}"),
                                     kind=CHECK_KIND["<kind>"], evidence=[ran.seq]))
        else:
            gate.checks.append(Check(
                kind, ran.ok, "" if ran.ok else str(ran.detail.get("tail", ""))[:200],
                kind=CHECK_KIND["<kind>"], evidence=[ran.seq],
            ))

    # Security: not run -> **unconfigured**, not passed. Omitting this check
    # when there are no results makes the gate silent exactly where it should
    # speak loudest. Reads `security` (review session result, parameter) not
    # events -> `evidence` is empty, and stated empty; `review` below is the
    # same (`review_blocking` is the reviewer's filtered verdict from `run_attempt`).
    if security is None:
        gate.checks.append(
            Check("security", Outcome.UNCONFIGURED, "security review not configured")
        )
    elif security.error:
        gate.checks.append(Check("security", False, security.error))
    else:
        chan = security.blocking(block_severities or DEFAULT_BLOCKING)
        gate.checks.append(Check(
            "security",
            not chan,
            "" if not chan else f"{len(chan)} blocking items: {chan[0].line()[:200]}",
        ))

    if not review_ran:
        gate.checks.append(Check("review", False, "independent review not run"))
    else:
        blocking = review_blocking or []
        gate.checks.append(
            Check(
                "review",
                not blocking,
                "" if not blocking else f"{len(blocking)} blocking items: {blocking[0][:200]}",
            )
        )

    gate.checks.append(_preservation_check(evidence, preservation or [], candidate))
    # `kind` is stamped from the table in one place, not scattered across checks;
    # names not in the table have no kind — test meta blocks unknown names,
    # so no guessing here.
    for c in gate.checks:
        c.kind = c.kind or CHECK_KIND.get(c.name, "")
    return gate


def _preservation_check(evidence: Evidence, preservation: list[dict], candidate: str) -> Check:
    """Check "preservation" (ADR-004 R4): VERIFIED behaviours of other stories
    whose files this story touches must **still be green at this candidate**.

    Three outcomes, no fourth. Red -> FAILED; the behaviour ledger infers
    REOPENED (`regressed_by` = this story) from the very evidence the gate
    reads, so no manual second write. No evidence at candidate — test doesn't
    carry the code, `qa` skipped, screen not compared — -> UNRUNNABLE:
    "unverifiable" is not "passed". The rest -> PASSED.

    Evidence must **carry the correct SHA**: events without a candidate
    (`for_candidate` retains them) must not be used here, because this check
    asks exactly "does this build break it", and a run of unknown build
    cannot answer that.
    """
    if not preservation:
        return Check("preservation", Outcome.NOT_APPLICABLE,
                     "story does not touch any VERIFIED behaviour of other stories")

    doc: list[int] = []     # events read at the correct candidate

    def at_candidate(kind: str, name: str):
        runs = [e for e in evidence.of(kind, name)
                if not candidate or str(e.detail.get("candidate") or "") == candidate]
        if runs and runs[-1].seq not in doc:
            doc.append(runs[-1].seq)
        return runs[-1] if runs else None

    test = at_candidate(TOOL_RUN, "test")
    ids = ([str(t) for t in test.detail.get("test_ids") or []]
           if test is not None and test.detail.get("test_format") else [])
    failed = {str(t) for t in test.detail.get("failed_ids") or []} if test is not None else set()

    do, thieu = [], []
    for it in preservation:
        bid, kind, owner = str(it.get("id") or ""), str(it.get("kind") or ""), str(it.get("story") or "")
        if kind == "ac":
            i = int(bid.rsplit("-", 1)[-1]) if bid.rsplit("-", 1)[-1].isdigit() else 0
            tests = ac_coverage(owner, i, ids).get(i, []) if i else []
        elif kind in ("fr", "nfr"):
            # Requirement green when criteria of the story **that verified it** are
            # green — same rule as the ledger (`source.story`), not the owning story on paper.
            via = str(it.get("via") or owner)
            tests = [t for t in ids if f"AC-{via}-" in t.replace("_", "-")]
        elif kind == "qa":
            ran = at_candidate(TOOL_RUN, bid)
            if ran is None or ran.detail.get("skipped"):
                thieu.append(bid)
            elif not ran.ok:
                do.append(bid)
            continue
        elif kind == "mockup":
            m = at_candidate(MOCKUP_MAP, bid.split(":", 1)[-1])
            if m is None:
                thieu.append(bid)
            elif not m.ok:
                do.append(bid)
            continue
        else:
            thieu.append(bid)
            continue
        if not tests:
            thieu.append(bid)
            continue
        red = [t for t in tests if t in failed]
        if red:
            do.append(f"{bid} ({red[0]})")

    if do:
        return Check("preservation", Outcome.FAILED,
                     f"regression: {', '.join(do[:3])}{'…' if len(do) > 3 else ''} — VERIFIED "
                     "behaviour of other stories is red at this candidate; fix code to make it green again, "
                     "do not modify their tests", evidence=doc)
    if thieu:
        return Check("preservation", Outcome.UNRUNNABLE,
                     f"cannot verify at candidate {candidate[:7] or 'this'}: "
                     f"{', '.join(thieu[:3])}{'…' if len(thieu) > 3 else ''} — no test "
                     "with code / check skipped / screen not compared; unverifiable is not a pass",
                     evidence=doc)
    return Check("preservation", True, f"{len(preservation)} behaviours of other stories still green", evidence=doc)


def qualification_table(test_file: Path | None = None) -> dict[str, dict[str, bool]]:
    """Gate check qualification table (ADR-005 V9, T10): name -> which controls exist.

    Reads the **AST** of `tests/test_gate_qualification.py` — classes with
    `TEN = "<name>"` and methods `test_positive*` / `test_negative*` /
    `test_env*` — not hand-copied into code, because a hand-copied table is
    a claim about tests, not a test. Installed from wheel has no `tests/`
    directory -> returns empty, report prints `?`, not 0 (0 means "counted,
    none found").
    """
    path = test_file or Path(__file__).resolve().parents[2] / "tests" / "test_gate_qualification.py"
    if not path.is_file():
        return {}
    table = {name: dict.fromkeys(CONTROLS, False) for name in CHECK_NAMES}
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if not isinstance(node, ast.ClassDef):
            continue
        ten = next((n.value.value for n in node.body
                    if isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant)
                    and any(isinstance(t, ast.Name) and t.id == "TEN" for t in n.targets)), None)
        if ten not in table:
            continue
        for fn in node.body:
            if isinstance(fn, ast.FunctionDef):
                for ctl in CONTROLS:
                    if fn.name.startswith(f"test_{ctl}"):
                        table[ten][ctl] = True
    return table
