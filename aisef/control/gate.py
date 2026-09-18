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
5. independent review has no blocking items — the one `model-judge` check, so
   the one check a person can override at a named candidate (`REVIEW_WAIVER`),
   which reads `WAIVED`, never `PASSED`;
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
from pathlib import Path, PurePosixPath

from ..harness.guardrails import check_completion, check_diff_scope
from .acceptance import (ac_code, coverage as ac_coverage, missing as ac_missing,
                         overloaded as ac_overloaded,
                         orphans as ac_orphans)
from .outcome import Check, Outcome
from .impact import is_test_path
from .tdd import proven_red_before_green
from .security import DEFAULT_BLOCKING
from .identity import CONTROL_FIELDS, SESSION_FIELDS, EvidenceIdentity, fresh  # noqa: F401
from ..harness.observe import FILE_CHANGE, GUARD_BLOCK, GUARD_SEEN, MOCKUP_MAP, NOTE, TOOL_RUN, Event, Evidence
from ..harness.testlog import MAX_IDS
from ..harness.tools import BASELINE_RUN, NO_MANIFEST, NO_SETUP, NOP_RUN
from . import proof

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

#: Human override of a **judge-only** block (closure gate G2.4b-iii). Written
#: by `aisef gate <story> --waive-review --reason ...` from a person's own
#: shell, read by `review_waiver()` below and **nowhere else**: the only check
#: a waiver can touch is `review`, the only `model-judge` entry in
#: `CHECK_KIND`. It is bound to the candidate SHA, so a new build is scored
#: from scratch, and it produces `WAIVED` — never `PASSED`.
#:
#: Why this exists: `review` is scored by a model, and the model's error rate
#: is measured, not hypothetical — miss 34-39 %, 11 of 20 consecutive reviews
#: of an identical tree reversed the verdict, and 21 of 57 recorded blocks
#: rested on the judge's word alone (`control/reviewer_qual.py`). Re-verify
#: deliberately **keeps** a blocking review conclusion at the same SHA, so
#: without this the only ways past a wrong block were to change the story or
#: abandon it. A probabilistic blocker with no override is a stop, not a gate.
REVIEW_WAIVER = "review:waiver"


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


def _stale_for(evidence: Evidence, current: EvidenceIdentity,
               kinds: tuple[str, ...] | None = None) -> dict[str, str]:
    """Checks whose evidence does not speak for `current`: no record fresh for this identity exists, yet a
    bound record does — the code, the tree, the contract or the configuration changed after the check.
    Keyed by check name, valued by the reason the latest bound record is not fresh. Sequence never decides:
    an older record fresh for this identity is valid, a newer foreign one is not staleness (CF-06)."""
    out: dict[str, str] = {}
    for key, latest in _latest_per_check(evidence, kinds).items():
        kind, name = key if isinstance(key, tuple) else (TOOL_RUN, key)
        if not EvidenceIdentity.of(latest, evidence.story_id).bound:
            continue          # never candidate-bound (a manual run, a legacy log): not staleness of this build
        if evidence.last_fresh(kind, name, current) is not None:
            continue
        out[name] = fresh(latest, current, story_id=evidence.story_id).reason
    return out


#: Where a verifier that did not execute used to be written (≤ 1.7.3): a finding whose text starts with this.
LEGACY_UNRUN = "review could not run:"
#: Tool runs that are UNBOUND BY CONSTRUCTION, not by age: the baseline describes the epoch's root, captured before
#: any candidate exists, and is compared against — never scored as — the candidate (INV-C.1). Every other unbound
#: tool run on the story path is a manual or ≤ 1.7.6 in-session run: shown, never scored (Phase 16).
UNBOUND_BY_DESIGN = ("test:baseline",)


def verdict_recorded(event: Event | None) -> bool:
    """Does this `tool_run review` / `tool_run security` carry a VERDICT (PASS or BLOCK)? A stage that did not
    execute writes a record too — `unrunnable`, an UNRUNNABLE `outcome`, or the ≤ 1.7.3 finding text — and that
    record is not evidence about the work (INV-F.3, INV-R.2; D-032, SS-07). The one definition, for the story loop
    (`_review_complete`) and the closure probe G4.4 alike."""
    if event is None:
        return False
    d = event.detail
    if d.get("unrunnable"):
        return False
    if str(d.get("outcome") or "").endswith("UNRUNNABLE"):
        return False
    return not any(str(f).startswith(LEGACY_UNRUN) for f in (d.get("findings") or []))


def _stale_candidates(evidence: Evidence, candidate: str,
                      kinds: tuple[str, ...] | None = None) -> list[str]:
    """Old candidates that the **latest result** of a check still refers to.

    Compared per check (kind + name), not per evidence file: the previous
    attempt leaving results at the old candidate is normal — rerunning on
    the new candidate is sufficient. What is abnormal is when the **latest**
    check still belongs to a different candidate: code changed after testing.

    ``kinds`` is this story's verification contract. Only checks the gate
    actually scores can make it stale — same reasoning as `ONE_SHOT_NAMES`,
    a different cause. A full `aisef qa` pass records `qa:unit`,
    `qa:security`, `qa:mutation` at whatever SHA it ran on; a story that
    declares none of them is never going to re-run them, so their records sit
    at an old candidate forever and every later story is declared stale
    (lỗi 136, measured on todo-oc where those three blocked a story whose own
    twelve records were all at the right build).
    """
    return sorted({str(e.detail["candidate"])
                   for e in _latest_per_check(evidence, kinds).values()
                   if str(e.detail["candidate"]) != candidate})


#: Records written **only** when something goes wrong — a role writes the tree
#: (`review:immutable`), reviews a moved build (`security:candidate`), the run
#: touches the trunk (`isolation`), the commit fails (`candidate:frozen`) —
#: and never re-written on a clean attempt. They are violation stamps, not
#: repeatable checks: counting them as checks means one old violation marks
#: every later build stale forever and the story can never pass —
#: todo/STORY-01-01 exhausted its attempts on a `review:immutable` recorded
#: three candidates earlier, after its cause was already fixed. Each still
#: blocks at the moment it fires; only the freshness scan ignores them.
#: Scored for every story regardless of its verification contract.
FAKE_TESTS = "qa:fake-tests"

#: Kinds a story may **declare** that never appear as a `qa:<kind>` check:
#: `unit` is the `test` tool's own run, `security` is the security review,
#: `mockup-map` is the screen comparison. `run_suite` does not run them and
#: the gate does not score them — so a `qa:` record of one, left at an old
#: build by a full `aisef qa` pass, must not make a story's evidence stale
#: either (lỗi 136). Named once so the two lists cannot drift apart.
KHONG_PHAI_QA = ("unit", "mockup-map", "security")

ONE_SHOT_NAMES = ("isolation", "candidate:frozen")
ONE_SHOT_SUFFIXES = (":immutable", ":candidate")


def _one_shot(name: str) -> bool:
    return name in ONE_SHOT_NAMES or name.endswith(ONE_SHOT_SUFFIXES)


def _latest_per_check(evidence: Evidence,
                      kinds: tuple[str, ...] | None = None) -> dict[tuple[str, str], Event]:
    """**Latest** result of each check (kind + name) that declares a candidate —
    exactly the events the "evidence matches candidate" check reads, so its
    `evidence` field points here.

    ``kinds`` given: `qa:<kind>` records outside this story's verification
    contract are skipped. `None` keeps every record (replay, old callers)."""
    moi_nhat: dict[tuple[str, str], Event] = {}
    for e in evidence.events:
        if not (e.kind in (TOOL_RUN, MOCKUP_MAP) and e.detail.get("candidate")
                and not _one_shot(e.name)):
            continue
        if (kinds is not None and e.name.startswith("qa:")
                and e.name != FAKE_TESTS
                and (e.name[3:] not in kinds or e.name[3:] in KHONG_PHAI_QA)):
            continue                      # not scored for this story
        moi_nhat[(e.kind, e.name)] = e
    return moi_nhat


def _head(tests: list[str], n: int = 5) -> str:
    return ", ".join(tests[:n]) + (f" (+{len(tests) - n})" if len(tests) > n else "")


def _flaky_ids(evidence: Evidence) -> list[str]:
    """Test names that changed outcome across k runs on the same SHA (`--repeat k`)."""
    note = evidence.last(NOTE, REPEAT_NOTE)
    return [str(t) for t in (note.detail.get("flaky_ids") or [])] if note else []


def _flaky_note(evidence: Evidence, name: str) -> str:
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
    flaky = _flaky_ids(evidence) if name == "test" else []
    if not flaky and name not in (d.get("flaky_checks") or []):
        return ""
    return (
        f"flaky across {d.get('k')} runs on the same SHA"
        + (f": {_head(flaky)}" if flaky else "")
        + " — unstable results are neither a failure nor a pass"
    )


def _class_of(test_id: str) -> str:
    """Leaf title of a test id: part after the last `>`, stripping leading `AC_...:` code."""
    leaf = test_id.rsplit(">", 1)[-1].strip()
    if ":" in leaf and leaf.split(":", 1)[0].replace("_", "-").upper().startswith("AC-"):
        leaf = leaf.split(":", 1)[1].strip()
    return leaf


def authoritative_baseline(evidence: Evidence, *, epoch: str | None = None) -> Event | None:
    """The story-entry baseline (D-033, lỗi 187): captured at the **integrated
    parent** when the story began, for the **current story epoch**. Never a
    record taken at the story's own candidate — a resumed run's worktree HEAD
    (LedgerLock STORY-03-01: seq 393, parent ca37cc44 ≠ base_ref 9cf22f5c) —
    and never one from an earlier contract.

    Epoch = the contract fingerprint (`story:contract` note, written by run.py
    when the criteria change). Records from 1.7.5 carry it as `epoch`; older
    records are trusted only when they stand at the branch point (`parent ==
    base_ref`, or no provenance recorded at all) and were recorded after the
    current contract note. Returns None when nothing qualifies — the caller
    tells "no baseline ever" (NOT_APPLICABLE) from "records exist, none
    authoritative" (UNRUNNABLE, fail closed)."""
    note = evidence.last(NOTE, "story:contract")
    if epoch is None and note is not None:
        epoch = str(note.detail.get("fingerprint") or "") or None
    events = list(evidence.events)
    note_pos = next((i for i, e in enumerate(events) if e is note), -1)
    chosen = None
    for pos, e in enumerate(events):
        if e.kind != TOOL_RUN or e.name != BASELINE_RUN:
            continue
        d = e.detail
        if "epoch" in d:
            if epoch and str(d.get("epoch")) != epoch:
                continue
            chosen = e
            continue
        if pos < note_pos:
            continue                     # a record from before the current contract
        parent, base_ref = str(d.get("parent") or ""), str(d.get("base_ref") or "")
        if parent and base_ref and parent != base_ref:
            continue                     # taken at the story's own build, not at the parent
        chosen = e
    return chosen


def _baseline_unavailable(name: str, evidence: Evidence) -> Check:
    last = evidence.last(TOOL_RUN, BASELINE_RUN)
    return Check(name, Outcome.UNRUNNABLE,
                 "BASELINE_UNAVAILABLE: baseline records exist but none was captured at the integrated "
                 "parent for this story epoch (last record: parent "
                 f"{str(last.detail.get('parent') or '?')[:8]}, base_ref "
                 f"{str(last.detail.get('base_ref') or '?')[:8]}) — a story never scores against its own "
                 "candidate; re-run the story from its base",
                 evidence=[last.seq])


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
    name = "no baseline regression"
    base_ev = authoritative_baseline(evidence)
    if base_ev is None:
        if evidence.last(TOOL_RUN, BASELINE_RUN) is not None:
            return _baseline_unavailable(name, evidence)
        return Check(name, Outcome.NOT_APPLICABLE,
                     "harness recorded no baseline (manual run, old journal) — cannot compare")
    seqs = [base_ev.seq]     # events read: baseline, then test run at candidate
    if base_ev.detail.get("disabled"):
        return Check(name, Outcome.NOT_APPLICABLE, "disabled by `verify.baseline` config", evidence=seqs)
    if base_ev.detail.get("skipped"):
        return Check(name, Outcome.UNCONFIGURED, f"no baseline: {base_ev.detail['skipped']}", evidence=seqs)
    if base_ev.detail.get("unrunnable"):
        # SS-85: "nothing ran" is evidence of nothing unless the tree held no project or no test at all — then there
        # was genuinely nothing green to protect. Tests that existed but could not run are simply unobserved.
        why = str(base_ev.detail["unrunnable"])
        if why == NO_MANIFEST or (why.startswith(NO_SETUP) and base_ev.detail.get("test_files_in_tree") == 0):
            return Check(name, Outcome.NOT_APPLICABLE,
                         f"the baseline commit had no {'project' if why == NO_MANIFEST else 'test file'} — nothing was "
                         f"ever green there, so there is nothing to regress ({why})", evidence=seqs)
        return Check(name, Outcome.UNRUNNABLE,
                     f"baseline did not execute ({why}) — the tests that existed there were never observed green, so "
                     "the comparison has nothing to stand on", evidence=seqs)
    if proof.aborted(base_ev.detail):
        return Check(name, Outcome.UNRUNNABLE,
                     "the baseline run stopped at collection — tests in files that did collect never ran, so which "
                     "were green there is unknown", evidence=seqs)
    if not base_ev.detail.get("test_format"):
        return Check(name, Outcome.UNCONFIGURED, str(base_ev.detail.get("test_note") or "")
                     or "cannot read test names from baseline — use a reporter that prints names "
                        "(`node --test`, `vitest --reporter=verbose`, `pytest -v`, CTRF)",
                     evidence=seqs)

    # Test run at candidate: after baseline, and matching the candidate being
    # scored (when candidate is given, reject manual runs without a candidate).
    # Tests *after* the baseline run — by position in the time-sorted event list,
    # not by ``seq``. ``seq`` reset mid-file (bug 42) makes numeric comparison
    # unsafe; position-after-sort is what "after" really means. Bug 47.
    post = [e for e in evidence.after_event(base_ev) if e.kind == TOOL_RUN and e.name == "test"
            and (not candidate or e.detail.get("candidate") == candidate)]
    if not post:
        return Check(name, False, "no test run at candidate after baseline — cannot compare",
                     evidence=seqs)
    latest = post[-1]
    seqs.append(latest.seq)
    if latest.detail.get("unrunnable"):
        return Check(name, Outcome.UNRUNNABLE,
                     f"candidate test run unrunnable ({latest.detail['unrunnable']}) — cannot compare",
                     evidence=seqs)
    if not latest.detail.get("test_format"):
        return Check(name, Outcome.UNCONFIGURED, str(latest.detail.get("test_note") or "")
                     or "cannot read test names at candidate — use a reporter that prints names", evidence=seqs)

    base_ids = list(base_ev.detail.get("test_ids") or [])
    base_executed_green = proof.executed_green(base_ev.detail)
    base_green = [t for t in base_ids if t in base_executed_green]
    # `--repeat k`: tests changing outcome across k runs at candidate are not
    # "broke" — the "test" check already records UNRUNNABLE naming them;
    # excluded here, and stated.
    flaky = _flaky_ids(evidence)
    # SS-86: not green = failed, errored OR skipped — a test green at baseline that no longer executes is not intact
    skipped_now = {str(t) for t in latest.detail.get("skipped_ids") or []} - set(flaky)
    red = proof.not_green(latest.detail) - set(flaky) - skipped_now
    current_ids = set(latest.detail.get("test_ids") or [])
    newly_red = [t for t in base_green if t in red]
    silenced = [t for t in base_green if t in skipped_now]
    # ponytail: testlog truncates list at MAX_IDS — test suites larger than
    # that cannot conclude "lost" (name may be beyond the cutoff), only compare red.
    cat = len(base_ids) >= MAX_IDS or len(current_ids) >= MAX_IDS
    # Rename != lost: same leaf title (part after last `>`) still present at
    # candidate means the test is still there, just under a different group/code
    # name. e9 01-07 attempt 2 (2026-09-06): developer added `AC_STORY_01_01_6:`
    # prefix to four existing tests to close GAPs of another story — gate read
    # it as "lost 4 tests". A real deletion loses the leaf title too, still caught.
    current_classes = {_class_of(t) for t in current_ids}
    renamed = [] if cat else [t for t in base_green if t not in current_ids and _class_of(t) in current_classes]
    lost = [] if cat else [t for t in base_green if t not in current_ids and _class_of(t) not in current_classes]
    if newly_red or lost or silenced:
        errors = []
        if newly_red:
            errors.append(f"broke {len(newly_red)} tests green at baseline: {_head(newly_red)}")
        if silenced:
            errors.append(f"silenced {len(silenced)} tests green at baseline — skipped at this candidate, so they no "
                          f"longer execute: {_head(silenced)} — un-skip them or declare the removal in the story")
        if lost:
            errors.append(f"lost {len(lost)} tests present at baseline: {_head(lost)} — deleting or renaming "
                       "existing tests must be declared in the story; evidence cannot infer intent "
                       "so this counts as regression")
        return Check(name, False, "; ".join(errors), evidence=seqs)
    if cat:
        # SS-33 / INV-T.1: beyond the cap a baseline-green test can turn red or vanish unseen — no vacuous PASS
        return Check(name, Outcome.UNRUNNABLE,
                     f"test list truncated at {MAX_IDS} names — the baseline comparison cannot see every test "
                     f"(baseline {len(base_ids)}, candidate {len(current_ids)}); split the suite or raise the cap",
                     evidence=seqs)
    pre_red = list(base_ev.detail.get("red_before") or base_ev.detail.get("failed_ids") or [])
    if renamed:
        return Check(name, True, f"{len(renamed)} tests renamed but leaf title still present, not counted as lost: {_head(renamed)}",
                     evidence=seqs)
    if pre_red:
        return Check(name, True, f"{len(pre_red)} tests already red at baseline, not counted: {_head(pre_red)}",
                     evidence=seqs)
    if flaky:
        return Check(name, True, f"{len(flaky)} flaky tests not counted here (see test check): {_head(flaky)}",
                     evidence=seqs)
    return Check(name, True, evidence=seqs)


def _nop_check(evidence: Evidence, story_id: str, *, acceptance: int, candidate: str,
               changed: list[str] | None = None) -> Check:
    """Check "tests verify story" — nop control (ADR-005 V3).

    The question from Terminal-Bench (nop < 1), BERBench (`base_fail`) and
    Agentless (reproduction test): **without the story's code, the story's
    tests must be red**. `TDD` only asks "was there any red run before the
    last green" — a syntax error red also passes. Here we ask directly at
    two levels, cheapest first:

    **Level 1 ($0, from `test:baseline` R9):** tests carrying `AC-<story>-i`
    green at candidate that were already green at baseline — same name, or old
    name gone but leaf title (`_class_of`) still present, meaning renamed to carry
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
    name = "tests verify story"
    base_ev = authoritative_baseline(evidence)
    if base_ev is None:
        # Only a record at the story's own build exists (a rerun): keep it so level 1
        # says "cannot compare" and level 2 decides — it never scores anything here.
        last = evidence.last(TOOL_RUN, BASELINE_RUN)
        if last is not None and str(last.detail.get("parent") or "") not in ("", str(last.detail.get("base_ref") or "")):
            base_ev = last
    # Same position-vs-seq reasoning as ``_baseline_check``: ``after_event``
    # for the events that came after the baseline, not numeric comparison.
    post = [e for e in evidence.after_event(base_ev) if e.kind == TOOL_RUN and e.name == "test"
            and (not candidate or e.detail.get("candidate") == candidate)] \
        if base_ev is not None \
        else list(evidence.of(TOOL_RUN, "test"))
    latest = post[-1] if post else None
    nop = evidence.last(TOOL_RUN, NOP_RUN)
    # Event pointers read: baseline, test run at candidate, nop — whichever exist.
    seqs = [e.seq for e in (base_ev, latest, nop) if e is not None]

    def check_result(outcome, detail: str = "", data: dict | None = None) -> Check:
        return Check(name, outcome, detail, evidence=seqs, data=data or {})

    # Tests with criteria codes **green** at candidate — subject of both levels.
    ac: list[str] = []
    if latest is not None and latest.detail.get("test_format") and acceptance > 0:
        new_green = [t for t in latest.detail.get("test_ids") or [] if t in proof.executed_green(latest.detail)]
        for tests in ac_coverage(story_id, acceptance, new_green).values():
            ac.extend(t for t in tests if t not in ac)

    # ---- level 1
    detail_note = ""
    if ac and base_ev is not None and base_ev.detail.get("test_format"):
        branch_ref, parent = str(base_ev.detail.get("base_ref") or ""), str(base_ev.detail.get("parent") or "")
        if branch_ref and parent and branch_ref != parent:
            detail_note = (f"level 1 cannot compare: baseline ran at {parent[:7]} — the story's own build "
                    f"(rerun), not the branch point {branch_ref[:7]}")
        else:
            base_ids = list(base_ev.detail.get("test_ids") or [])
            not_green = set(base_ev.detail.get("failed_ids") or []) | set(base_ev.detail.get("skipped_ids") or [])
            base_green = {t for t in base_ids if t not in not_green}
            current_ids = set(latest.detail.get("test_ids") or [])
            near_match = [t for t in ac if t in base_green]
            cat = len(base_ids) >= MAX_IDS or len(current_ids) >= MAX_IDS
            if cat:
                # SS-33 / INV-T.1: the rename detection cannot see past the cap — state it, never conclude
                return Check(name, Outcome.UNRUNNABLE,
                             f"test list truncated at {MAX_IDS} names — cannot tell tagged or renamed existing tests "
                             f"from new ones", evidence=seqs)
            lost_classes = {_class_of(t) for t in base_green if t not in current_ids}
            # not `changed`: that name is the story's file list, which level 2 binds import failures to
            renamed = [t for t in ac if t not in base_ids and _class_of(t) in lost_classes]
            errors = []
            if near_match:
                errors.append(f"tagged existing tests: {len(near_match)} tests with criteria codes were already green at "
                           f"baseline under the same name — green before the story wrote a line: {_head(near_match)}")
            if renamed:
                errors.append(f"renamed existing tests to carry codes: {len(renamed)} tests were green at baseline under "
                           f"their old name — criteria code became a label, not a verification: {_head(renamed)}")
            if errors:
                return check_result(False, "; ".join(errors) + ". Write new tests for criteria, keep existing tests under their original names")

    # ---- level 2 — the proof model (SS-81 family, INV-TDD-NOP-PROOF): PASS only on positive, per-test evidence
    # that every criterion test green at the candidate is red at the parent. Absence of execution is never proof.
    readable = latest is not None and bool(latest.detail.get("test_format"))
    if nop is None:
        if acceptance <= 0:
            return check_result(Outcome.NOT_APPLICABLE, "harness ran no nop and the story declares no criteria")
        if not readable:
            return check_result(Outcome.UNCONFIGURED, "cannot read test names at the candidate, and no nop control was "
                                                      "recorded — use a reporter that prints names (`pytest -v`, …)")
        # SS-89: the control never ran for this candidate — that is not "not applicable"
        return check_result(Outcome.UNRUNNABLE, "no nop control was recorded for this candidate — the story's tests "
                                                "were never run at the parent SHA, so nothing shows they verify it")
    d = nop.detail
    if d.get("disabled"):
        return check_result(Outcome.NOT_APPLICABLE, "disabled by `verify.nop` config")
    if d.get("skipped"):
        if "files" in d and not d["files"]:
            return check_result(Outcome.NOT_APPLICABLE, "story did not add/modify test files")
        return check_result(Outcome.UNCONFIGURED, f"no nop: {d['skipped']}")
    parent = str(d.get("parent") or "")[:7] or "cha"
    if acceptance <= 0:             # SS-84: a red parent run proves nothing about criteria that do not exist
        return check_result(Outcome.UNRUNNABLE, "story declares no criteria — no criterion test exists for the control to "
                                                f"prove red at parent SHA {parent}")
    if d.get("unrunnable") and not d.get("test_format") and not d.get("collection_errors"):
        # The control did not execute at all. Only one such case is proof: the parent has no project, and THIS story
        # is what creates it — no test of the project could have passed where the project did not exist.
        made = [f for f in d.get("absent_at_parent") or [] if PurePosixPath(f).name.lower() in proof.MANIFESTS]
        if str(d["unrunnable"]) == NO_MANIFEST and made:
            return check_result(True, f"parent SHA {parent} has no project at all — this story creates it ({made[0]}), "
                                      "so none of its tests can have been green there")
        return check_result(Outcome.UNRUNNABLE,
                            f"nop at parent SHA unrunnable ({d['unrunnable']}) — the control did not execute, so it proves nothing")
    if latest is None:
        return check_result(False, "no test run at candidate — cannot determine which tests are green to compare with parent SHA")
    if not readable:
        if nop.ok:              # positive evidence even without names: the whole suite passed with the story's tests in
            return check_result(False, f"test suite green at parent SHA {parent} with story test files copied in — "
                                       f"story tests verify nothing ({_head(list(d.get('files') or []), 3)})")
        return check_result(Outcome.UNCONFIGURED,
                            "cannot read test names at the candidate — the control needs the criterion tests by name; use a "
                            "reporter that prints names (`node --test`, `vitest --reporter=verbose`, `pytest -v`)")
    if not ac:
        return check_result(False, "no tests with criteria codes green at candidate — nothing "
                                 "to verify at parent SHA (see criteria have tests check)")
    story_files = [f for f in (changed or []) if not is_test_path(f)]
    states = proof.classify(d, ac, story_files, added=d.get("absent_at_parent"),
                            files=proof.files_of(ac, story_id, acceptance, d.get("ac_code_files")))
    per_ac = proof.summarize(states, story_id, acceptance)
    data = {"parent": parent, "proof": per_ac, "strategy": d.get("collection_strategy") or ""}
    still_green = [t for t, (p, _) in states.items() if p is proof.Proof.GREEN_EXECUTED]
    if still_green:
        return check_result(False, f"tests verify nothing — still green without story code "
                                   f"(parent SHA {parent}): {_head(still_green)}",
                            data={**data, "still_green": list(still_green)})   # SS-32: data, not a sentence
    if d.get("output_complete") is False:
        return check_result(Outcome.UNRUNNABLE, f"the nop output at parent SHA {parent} is incomplete — its own totals do "
                                                "not match the tests read, so nothing it omits can count as red", data=data)
    unproven = {t: st for t, st in states.items() if st[0] not in proof.PROVES_RED}
    if unproven:
        head = "; ".join(f"{t} — {p.value}: {why}" for t, (p, why) in list(unproven.items())[:3])
        return check_result(Outcome.UNRUNNABLE,
                            f"no proof at parent SHA {parent} for {len(unproven)} of {len(ac)} criterion tests: {head}"
                            + ("…" if len(unproven) > 3 else ""), data=data)
    ran = sum(1 for p, _ in states.values() if p is proof.Proof.RED_EXECUTED)
    return check_result(True, f"{len(ac)} tests with criteria codes proven red at parent SHA {parent}: {ran} executed red, "
                              f"{len(ac) - ran} unable to import code this story introduces"
                              + (f"; {detail_note}" if detail_note else ""), data=data)


def judge_only(gate: StoryGate) -> bool:
    """Did the **judge alone** stop this story? (closure gate G2.4b-i)

    True when the gate blocked and `review` — the single `model-judge` entry in
    `CHECK_KIND` — is the only blocking check. This is the question an operator
    has to be able to ask of a verdict ("was anything deterministic behind
    this?"), and the answer is one comparison over one record, not a re-read of
    the reviewer's prose. `gate:verdict` stores `failures` and every check's
    `outcome`, so the same comparison works on evidence months later.

    `UNRUNNABLE` counts as blocking here, because `Outcome.blocks` says it
    does: a story also held up by a check that could not run was not stopped by
    the judge alone, and calling it judge-only would overstate the override's
    reach.
    """
    return [c.name for c in gate.failures] == ["review"] and all(
        c.outcome is not Outcome.UNRUNNABLE for c in gate.failures)


def review_waiver(evidence: Evidence, candidate: str) -> Event | None:
    """The human override in force for **this** candidate, or None (G2.4b-iii).

    Three conditions, all cheap and all necessary. A waiver needs a
    ``candidate``, because a person judged one diff and not the next build; it
    needs a non-empty ``reason``, the same rule `approvals.reject` already
    applies to a rejection note; and the latest one wins, so a second signature
    can correct the first without editing the record.
    """
    if not candidate:
        return None
    return next((e for e in reversed(evidence.of(NOTE, REVIEW_WAIVER))
                 if str(e.detail.get("candidate") or "") == candidate
                 and str(e.detail.get("reason") or "").strip()), None)


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
    review_unrunnable: str = "",
    security=None,
    block_severities=None,
    guard_expected: bool = False,
    acceptance: int = 0,
    coverage_min: float | None = None,
    added_tests: list[str] | None = None,
    candidate: str = "",
    preservation: list[dict] | None = None,
    identity: EvidenceIdentity | None = None,
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
    # The state being decided on. A story attempt passes its full identity (control/identity.py); a manual
    # `aisef gate` passes a candidate only, and then binds on nothing but the candidate (legacy mode).
    story_path = identity is not None
    current = identity if identity is not None else EvidenceIdentity(story_id=story_id, candidate_sha=candidate)
    if story_path:
        candidate = current.candidate_sha

    loai = tuple(contract or ())
    moi_nhat = _latest_per_check(evidence, loai)
    stale = _stale_for(evidence, current, loai) if candidate else {}
    if not candidate and story_path:
        # A story attempt without a frozen candidate: nothing can be graded (SS-60, SS-A15). Only a manual
        # `aisef gate` with no candidate is "not applicable".
        gate.checks.append(Check(
            "evidence matches candidate", Outcome.UNRUNNABLE,
            "no candidate was frozen for this attempt — nothing can be graded; the freeze failed or HEAD is unreadable",
        ))
    elif not candidate:
        gate.checks.append(Check(
            "evidence matches candidate", Outcome.NOT_APPLICABLE,
            "no candidate passed — cannot verify which build evidence belongs to",
        ))
    elif stale:
        gate.checks.append(Check(
            "evidence matches candidate", Outcome.UNRUNNABLE,
            "stale: " + "; ".join(f"{name}: {why}" for name, why in list(stale.items())[:4])
            + f" — current candidate is {candidate[:7]}; rerun those checks on this build",
            evidence=[e.seq for key, e in moi_nhat.items() if (key[1] if isinstance(key, tuple) else key) in stale],
        ))
    else:
        gate.checks.append(Check("evidence matches candidate", True,
                                 evidence=[e.seq for e in moi_nhat.values()]))
    if candidate:
        # After stating it, drop evidence that is not fresh for this identity: a check from another build,
        # another tree state or another configuration must not silently make any check pass.
        evidence = evidence.for_identity(current)
        if story_path:
            # Phase 16: an UNBOUND tool run — no candidate, no session: a manual `aisef tool`, or a ≤ 1.7.6
            # in-session run — can be shown, never scored for a story attempt; it speaks for no build. Measured
            # on the archived 1.7.4 replays: `test`, `lint` and `security` scored PASSED from such records.
            evidence = Evidence(story_id=evidence.story_id,
                                events=[e for e in evidence.events
                                        if e.kind != TOOL_RUN or e.name in UNBOUND_BY_DESIGN
                                        or EvidenceIdentity.of(e, evidence.story_id).bound])

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
        # First trace is enough to answer "did the hook fire" — of THIS session (SS-02): a heartbeat left by
        # an earlier attempt proves nothing about the session that produced this candidate.
        traces = evidence.of(GUARD_SEEN) + evidence.of(GUARD_BLOCK) + evidence.of(FILE_CHANGE)
        if current.session_id:
            traces = [e for e in traces if fresh(e, current, SESSION_FIELDS).ok]
        dau_vet = traces[:1]
        reached = bool(traces)
        gate.checks.append(Check(
            "guard ran", reached,
            "" if reached else (
                "guard did not evaluate any write in this session — hook cannot "
                "reach worktree? (.claude/ not committed, or --settings not "
                "passed). A story that writes nothing also lands here, and that is correct."
            ),
            evidence=[dau_vet[0].seq] if dau_vet else [],
        ))

    completion = check_completion(evidence)
    last_test = evidence.last(TOOL_RUN, "test")
    # `completion` reads the last test run and files edited **after** it — point to both.
    doc_test = ([last_test.seq] + [e.seq for e in evidence.after_event(last_test) if e.kind == FILE_CHANGE]
                if last_test is not None else [])
    flaky = _flaky_note(evidence, "test")
    if last_test is not None and last_test.detail.get("unrunnable"):
        gate.checks.append(Check("test", Outcome.UNRUNNABLE, str(last_test.detail["unrunnable"]),
                                 evidence=doc_test))
    elif flaky:
        gate.checks.append(Check("test", Outcome.UNRUNNABLE, flaky, evidence=doc_test))
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
    elif lint.detail.get("unrunnable"):
        # a linter that is not there is not a red lint (SS-58 — D-029's shape on the lint tool)
        gate.checks.append(
            Check("lint", Outcome.UNRUNNABLE, str(lint.detail["unrunnable"])[:300], evidence=[lint.seq])
        )
    elif _flaky_note(evidence, "lint"):
        gate.checks.append(Check("lint", Outcome.UNRUNNABLE, _flaky_note(evidence, "lint"),
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
            # Rendering unavailable (no node, no playwright) is not a mismatch
            # and not a pass: nothing was compared. Naming it keeps the reader
            # from reading ✅ as "the screen matches the mockup".
            khong_chay = [s for s in screens if maps[s].detail.get("unavailable")]
            failed = [s for s in screens if not maps[s].ok and s not in khong_chay]
            detail = ""
            if failed:
                first = maps[failed[0]].detail
                detail = (
                    f"{failed[0]} missing: "
                    + ", ".join(first.get("missing", []) + first.get("missing_data_roles", []))
                )
                # Name the near-match. "missing textbox X" sends the author
                # hunting for a field that is on the screen under another
                # label — todo/STORY-02-01 spent all three attempts that way.
                doi_ten = first.get("renamed") or []
                if doi_ten:
                    detail += " — on screen as " + ", ".join(
                        f"{co}" for _, co in doi_ten
                    ) + "; the mockup pins the accessible name (rename back, or change the mockup and re-approve)"
            if failed:
                gate.checks.append(Check("mockup map", False, detail, evidence=doc_map))
            elif khong_chay:
                gate.checks.append(Check(
                    "mockup map", Outcome.UNCONFIGURED,
                    f"{', '.join(khong_chay)} not compared: "
                    + str(maps[khong_chay[0]].detail["unavailable"])[:200],
                    evidence=doc_map))
            else:
                gate.checks.append(Check("mockup map", True, evidence=doc_map))

    fake = evidence.last(TOOL_RUN, FAKE_TESTS)
    if fake is not None and not fake.ok:
        files = fake.detail.get("files") or []
        gate.checks.append(
            Check("real tests", False,
                  f"{len(files)} tests have no assertions: {', '.join(files[:3])}",
                  evidence=[fake.seq])
        )
    elif fake is None:
        # SS-01 / INV-T.1: "the scan never ran" must not read like "the scan ran clean"
        gate.checks.append(Check("real tests", Outcome.UNRUNNABLE,
                                 f"no `{FAKE_TESTS}` record — the assertion scan did not run for this candidate"))
    else:
        gate.checks.append(Check("real tests", True, evidence=[fake.seq]))

    # Criteria have tests (G5): `AC-<story>-<i>` code must appear in the name
    # of a test in the last green run — names read from runner output, not
    # agent claims. Cannot read test names -> **unconfigured** reporter, not
    # a story fault and not a pass.
    green = [e for e in evidence.of(TOOL_RUN, "test") if e.ok]
    last_green = green[-1] if green else None
    doc_xanh = [last_green.seq] if last_green is not None else []
    if acceptance <= 0:
        gate.checks.append(Check("criteria have tests", Outcome.NOT_APPLICABLE, "story declares no criteria"))
    elif last_green is None and last_test is not None and last_test.detail.get("unrunnable"):
        # the runner itself could not run: no test evidence exists either way — an absence, not a red story
        # (INV-F.3; a derived FAILED here would reopen the developer for an environment fault, SS-14)
        gate.checks.append(Check("criteria have tests", Outcome.UNRUNNABLE,
                                 "no test run could execute — see `test`", evidence=[last_test.seq]))
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
        # Names from **every** green suite at this candidate that printed them,
        # not only the unit runner. A story whose acceptance criteria are
        # browser behaviour can only name them in e2e titles, and reading the
        # unit runner alone made that story unsatisfiable — measured on a
        # single-screen browser app that never passed a story in three runs,
        # where the agent read the harness's own source to work out why
        # (lỗi 132). The requirement does not move: each criterion still needs
        # a test bearing its code, green at this build. A red suite contributes
        # nothing, and neither does a failed test inside a green one.
        phu: dict[str, list[str]] = {}
        for e in evidence.of(TOOL_RUN):
            if not e.ok or not e.name.startswith("qa:"):
                continue
            if candidate and not EvidenceIdentity.of(e).bound:
                continue          # SS-03: an unstamped run proves nothing about this build
            hong = {str(x) for x in (e.detail.get("failed_ids") or [])}
            ids = [str(t) for t in (e.detail.get("test_ids") or []) if str(t) not in hong]
            if ids:
                phu[e.name] = ids
        tat_ca = list(last_green.detail.get("test_ids") or [])
        for ids in phu.values():
            tat_ca.extend(ids)
        missing = ac_missing(story_id, acceptance, tat_ca)
        # Lỗi 159: `missing` chỉ hỏi "tiêu chí nào thiếu phép thử". Sau khi một
        # tiêu chí bị rút, mọi mã sau nó tụt một bậc và câu ấy trả **rỗng** —
        # mỗi tiêu chí vẫn có phép thử mang mã đúng, chỉ là phép thử ấy chứng
        # minh hành vi khác. Mã mồ côi (i > số tiêu chí) là dấu vết duy nhất của
        # sự dịch chuyển còn đọc được từ dữ liệu, nên nó **chặn**: một mục cấu
        # trúc không được đạt khi danh tính của bằng chứng đã trượt.
        mo_coi = ac_orphans(story_id, acceptance, tat_ca)
        # Lỗi 159, đường thứ ba: **một** phép thử mang **hai** mã thoả cả hai
        # tiêu chí bằng một hành vi. Không phép đếm nào bắt được — `missing` rỗng
        # và không mã nào mồ côi — nên nó phải được hỏi riêng.
        nhap_nhang = ac_overloaded(story_id, tat_ca)
        lenh = str(last_green.detail.get("command") or "tools.test")
        nguon = ", ".join([f"`{lenh}`", *(f"`{k}`" for k in sorted(phu))])
        gate.checks.append(Check(
            "criteria have tests", not missing and not mo_coi and not nhap_nhang,
            (f"tests carry codes with no criterion: {', '.join(mo_coi)} — the story "
             f"has {acceptance} criteria, so a test named after a higher code proves "
             f"nothing this story declares, and every code at or below it may have "
             f"shifted onto a different criterion. Re-tag the tests, or restore the "
             f"criteria the codes were written for (lỗi 159)."
             ) if mo_coi and not missing else
            ("; ".join(
                f"`{t}` carries {', '.join(ma)}" for t, ma in sorted(nhap_nhang.items()))
             + " — one test cannot be the proof for more than one criterion: it "
               "demonstrates one behaviour, so each code it carries is credited from "
               "evidence written for another. Give each criterion its own test (lỗi 159)."
             ) if nhap_nhang and not missing else
            "" if not missing else
            f"no tests with codes {', '.join(ac_code(story_id, i) for i in missing)} — "
            f"each criterion needs at least one test named after its code, green at "
            f"this build. Names were read from {nguon}"
            + ("" if phu else
               " — no other suite recorded test names at this candidate, so if the "
               "codes are in e2e titles, check that the e2e run is in this story's "
               "verification contract and that its reporter prints names"),
            evidence=doc_xanh + [e.seq for e in evidence.of(TOOL_RUN)
                                 if e.name in phu],
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

    # Nop control (ADR-005 V3) asks TDD's question directly, so it is computed
    # first even though it is reported second: when it has actually run and
    # passed, the story's tests are **proven** red without the story's code —
    # which is what red-before-green is a proxy for. A proxy must not block
    # what the direct measurement cleared (lỗi 118): on todo-cli STORY-01-02
    # the nop control passed ("5 tests with criteria codes are red or absent
    # at parent SHA") while `TDD` failed, and the story was blocked by the
    # weaker of the two. Only `PASSED` counts — NOT_APPLICABLE, UNRUNNABLE and
    # UNCONFIGURED mean the control did not answer, so `TDD` stands alone.
    nop = _nop_check(evidence, story_id, acceptance=acceptance, candidate=candidate, changed=changed)

    # TDD (G8): story added tests must have a red run before the last green. SS-83: "red" is read through the same
    # proof model as the nop control — a run that could not execute, or that is red only because of an unrelated test,
    # shows nothing about the story's tests.
    if added_tests is not None:
        red_run = proven_red_before_green(evidence, story_id, acceptance=acceptance, added_tests=added_tests,
                                          changed=changed) if added_tests else None
        if not added_tests:
            gate.checks.append(Check("TDD", Outcome.NOT_APPLICABLE, "story did not add tests"))
        elif red_run is not None:
            gate.checks.append(Check(
                "TDD", True, f"red before green: run #{red_run.seq} shows the story's tests red for a reason the "
                             f"story's code decides",
                evidence=[e.seq for e in evidence.of(TOOL_RUN, "test")],   # red/green order read across full sequence
            ))
        elif nop.outcome is Outcome.PASSED:
            gate.checks.append(Check(
                "TDD", True,
                f"no red run recorded, but the nop control proves the same thing "
                f"directly — {nop.detail or 'story tests are red without the story code'}",
                evidence=list(nop.evidence),
            ))
        else:
            gate.checks.append(Check(
                "TDD", False,
                f"tests green on first run — not proven to verify anything "
                f"({', '.join(added_tests[:3])}). Write tests first, run them through "
                f"the recorded tool, see them fail, then write code — a run the harness "
                f"did not record cannot prove anything.",
                evidence=[e.seq for e in evidence.of(TOOL_RUN, "test")],
            ))
    gate.checks.append(nop)

    # Story verification contract. Unconfigured kinds are recorded as
    # **unconfigured**, not passed — they block at the pre-deploy gate, and
    # here they must be visible so the reader knows where the gap is.
    for kind in contract or []:
        if kind in KHONG_PHAI_QA:
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
        elif ran.detail.get("unrunnable"):                               # SS-34: the runner did not run — not a verdict
            gate.checks.append(Check(kind, Outcome.UNRUNNABLE, str(ran.detail["unrunnable"])[:200],
                                     kind=CHECK_KIND["<kind>"], evidence=[ran.seq]))
        elif _flaky_note(evidence, f"qa:{kind}"):
            gate.checks.append(Check(kind, Outcome.UNRUNNABLE, _flaky_note(evidence, f"qa:{kind}"),
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
    elif getattr(security, "unrunnable", ""):
        # The security reviewer did not execute: no verdict exists about this candidate. UNRUNNABLE blocks
        # (fail closed) and names the execution failure, so the loop retries the SECURITY stage, never the
        # developer (SS-13 — D-032's rule on the security stage).
        gate.checks.append(Check("security", Outcome.UNRUNNABLE,
                                 f"security reviewer did not run ({security.unrunnable}) — no verdict about the candidate"))
    elif security.error:
        gate.checks.append(Check("security", False, security.error))
    else:
        blocking = security.blocking(block_severities or DEFAULT_BLOCKING)
        gate.checks.append(Check(
            "security",
            not blocking,
            "" if not blocking else f"{len(blocking)} blocking items: {blocking[0].line()[:200]}",
        ))

    if review_unrunnable:
        # The reviewer did not execute: no verdict exists about this candidate.
        # UNRUNNABLE blocks (fail closed) and names the execution failure, so
        # the retry loop retries the REVIEW stage instead of the developer,
        # and nobody is invited to waive a check that never ran (D-032).
        gate.checks.append(Check("review", Outcome.UNRUNNABLE,
                                 f"reviewer did not run ({review_unrunnable}) — no verdict about the candidate"))
    elif not review_ran:
        gate.checks.append(Check("review", False, "independent review not run"))
    else:
        blocking = review_blocking or []
        mien = review_waiver(evidence, candidate) if blocking else None
        if mien is not None:
            gate.checks.append(Check(
                "review", Outcome.WAIVED,
                f"{len(blocking)} blocking items waived by "
                f"{mien.detail.get('by') or 'unknown'}: {mien.detail.get('reason')} "
                f"— first item: {str(blocking[0])[:160]}",
                evidence=[mien.seq],
            ))
        else:
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

    seqs: list[int] = []     # events read at the correct candidate

    def at_candidate(kind: str, name: str):
        runs = [e for e in evidence.of(kind, name)
                if not candidate or str(e.detail.get("candidate") or "") == candidate]
        if runs and runs[-1].seq not in seqs:
            seqs.append(runs[-1].seq)
        return runs[-1] if runs else None

    test = at_candidate(TOOL_RUN, "test")
    ids = ([str(t) for t in test.detail.get("test_ids") or []]
           if test is not None and test.detail.get("test_format") else [])
    failed = {str(t) for t in test.detail.get("failed_ids") or []} if test is not None else set()
    # SS-87: a skipped or errored test did not execute — a behaviour resting on it is unobserved, not still green
    unexecuted = (proof.not_green(test.detail) - failed) if test is not None else set()

    broken, missing = [], []
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
                missing.append(bid)
            elif not ran.ok:
                broken.append(bid)
            continue
        elif kind == "mockup":
            m = at_candidate(MOCKUP_MAP, bid.split(":", 1)[-1])
            if m is None or m.detail.get("unavailable"):
                missing.append(bid)      # not compared ≠ broken
            elif not m.ok:
                broken.append(bid)
            continue
        else:
            missing.append(bid)
            continue
        if not tests:
            missing.append(bid)
            continue
        red = [t for t in tests if t in failed]
        if red:
            broken.append(f"{bid} ({red[0]})")
            continue
        if all(t in unexecuted for t in tests):
            missing.append(f"{bid} (not executed: {tests[0]})")

    if broken:
        return Check("preservation", Outcome.FAILED,
                     f"regression: {', '.join(broken[:3])}{'…' if len(broken) > 3 else ''} — VERIFIED "
                     "behaviour of other stories is red at this candidate; fix code to make it green again, "
                     "do not modify their tests", evidence=seqs)
    if missing:
        return Check("preservation", Outcome.UNRUNNABLE,
                     f"cannot verify at candidate {candidate[:7] or 'this'}: "
                     f"{', '.join(missing[:3])}{'…' if len(missing) > 3 else ''} — no test "
                     "with code / check skipped / screen not compared; unverifiable is not a pass",
                     evidence=seqs)
    return Check("preservation", True, f"{len(preservation)} behaviours of other stories still green", evidence=seqs)


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
    return controls_in(path, CHECK_NAMES)


def controls_in(path: Path, names: tuple[str, ...]) -> dict[str, dict[str, bool]]:
    """Which of the three controls `path` holds for each name in `names`.

    The AST walk shared by `qualification_table()` and the reviewer-judgement
    table (`control/reviewer_qual.py`, ADR-009 O1): both read a test file for
    classes carrying `TEN = "<name>"` and methods prefixed `test_positive` /
    `test_negative` / `test_env`. One reader, so the two tables cannot mean
    different things by "has a control".
    """
    if not path.is_file():
        return {}
    table = {name: dict.fromkeys(CONTROLS, False) for name in names}
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if not isinstance(node, ast.ClassDef):
            continue
        name = next((n.value.value for n in node.body
                    if isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant)
                    and any(isinstance(t, ast.Name) and t.id == "TEN" for t in n.targets)), None)
        if name not in table:
            continue
        for fn in node.body:
            if isinstance(fn, ast.FunctionDef):
                for ctl in CONTROLS:
                    if fn.name.startswith(f"test_{ctl}"):
                        table[name][ctl] = True
    return table
