# Post-1.0 Roadmap

## Experimental memory follow-up (2026-09-11) — superseded 2026-09-12

Local scoped advisory memory is implemented but default OFF. [P0/P1/P2 research plan](MEMORY-RESEARCH-PLAN.md), [ADR-007](ADR-007-scoped-advisory-memory.md), [operational guide](MEMORY.md), [validation report](MEMORY-VALIDATION.md). Pending: independently reviewed security hardening, verified OpenViking protocol adapter, authorized paired long-horizon real-agent efficacy (primary repeated-error rate), signed promotion/global sharing. Scripted retrieval success is not an enablement criterion.

> **Status correction (2026-09-14).** The paragraph above reads as an open
> research queue; it is not one any more. [ADR-007 § Addendum — frozen
> (2026-09-12)](ADR-007-scoped-advisory-memory.md#addendum--frozen-2026-09-12)
> moved the feature from *EXPERIMENTAL, default OFF* to **FROZEN, default OFF**:
> code stays, bug and security fixes continue, **no new capability** — so the
> "pending" items above are not scheduled work. Two measurements drove it: no
> retrieval-scorer candidate beat the current word-overlap scorer on both of two
> opposed datasets ([MEMORY-BENCH](MEMORY-BENCH.md)), and no external user has
> run the lifecycle, so a default-OFF feature produces no demand signal. Thaw
> condition, quoted: an external user asks for it, **or** a paired measurement
> on a real agent shows a repeated error the memory would have prevented.

> **2026-09-14 — this file is not a gate, and the closure contract says so
> explicitly.** [`PROJECT-CLOSURE-GATE.md`](PROJECT-CLOSURE-GATE.md) (owner-
> approved 2026-09-14) is the sole authoritative definition of "project
> finished". This roadmap remains a **priority list**, and its §8 rules six
> items here POST_CLOSE with reasons rather than blocking on them for appearing
> on a roadmap: benchmark expansion to ≥3 languages/task classes (#4),
> behaviour-scoped preservation, distributed execution (#5), the PyPI
> organisation account, skill scanning, and CLI optimisation. Item **#1
> (external user validation)** is the exception — it is closure gate **G6**, and
> the chicken-and-egg argument ADR-006 §2 used to defer it has expired now that
> v1.0.0–v1.6.0 are published.

Written 2026-09-08, after v1.0.0 release. Items prioritized by evidence
from dogfood runs, conformance, and known limitations — not by feature wish.

---

## Cross-tier invariants (2026-09-12)

Three of the seven systemic issues surfaced in the pre-Phase-2 audit
were transactional defects that are now closed: structured findings
(anti-goalpost reviewer), candidate-bound dev-server identity lease,
and in-flight budget reservation.  Two follow-up defects in the
budget seam were caught by the wire-up harness on the same day and
closed by switching the lock carrier to a sidecar and counting
in-flight reservations in the cap math.  See
[ADR-009](ADR-009-phase-3-cross-tier-invariants.md#follow-up-two-cross-tier-defects-in-the-budget-seam).
The other four issues are *semantic* and depended on these being
correct first.  **All four closed 2026-09-14**, each with its
measurement, in
[ADR-009 § The four semantic issues](ADR-009-phase-3-cross-tier-invariants.md#the-four-semantic-issues-reconstructed-2026-09-12):
reviewer verdicts are not themselves qualified (O1 — `aisef/control/reviewer_qual.py`,
scored over 145 recorded sessions), the ledger does not record what
*kind* of gap a GAP is (O2 — `Behavior.gap_kind`, repair queue routed
by kind), preservation scoped by file rather than by behaviour
(O3 — the neighbour weight calibrated and left at 0 with the table in
[ADR-009 § O3](ADR-009-phase-3-cross-tier-invariants.md#o3--preservation-is-scoped-by-file-not-by-behaviour--closed-2026-09-14)),
and spend attributed to calls rather than to outcomes (O4 — the
`aisef cost` verb).  Settle any of them without a model call:

```
python3 -c "import aisef.control.reviewer_qual"                          # O1
python3 -c "from aisef.control.ledger import Behavior, gap_kind_counts"  # O2
grep -n 'story.verified_touched_weight' aisef/config.py                 # O3 → 4 lines
python3 -m aisef.cli cost --help                                        # O4 → usage: aisef cost …
```

*Until 2026-09-14 this paragraph listed O1, O2 and O4 as still open
("Each carries the measurement that closes it", future tense) and
named only O3 as closed.  That was the state for part of one day; the
last of the four merged the same afternoon.*

## 1. External user validation

**Problem:** v1.0.0 shipped without any external user running the framework
independently. All evidence is internal.

**Evidence:** ADR-006 §2 documents the chicken-and-egg: users won't adopt
a framework that never ships.

**Expected value:** Confidence that the harness works outside its creator's
mental model. Real friction points surfaced.

**Proposed solution:** Publish clear onboarding docs, share with 1–2 trusted
teams/developers, collect structured feedback.

**Verification:** At least 1 project run end-to-end by someone who did not
build the framework. Record their setup time, friction points, gate pass rate.

**Priority:** P0 — the single most important post-1.0 activity.
**Effort:** Low (framework side); depends on finding willing users.
**Risk:** No volunteers; framework assumptions don't hold outside author's projects.
**Release target:** v1.1.0

---

## 2. Stronger credential isolation (local provider) — **CLOSED by decision, ADR-011** (2026-09-13)

**Problem:** Local sandbox provider honestly reports `unsupported` for S1–S4.
Docker works but adds setup friction.

**Evidence:** `tests/sandbox_conformance.py` — Docker **5/5**, Local **2/5**
(S3 "no write outside workspace" ✅ and S5 "timeout leaves no process" ✅; S1,
S2, S4 ✗ — see the measured table in [SANDBOX-CONFORMANCE](SANDBOX-CONFORMANCE.md),
run 2026-09-06). *The "Local 1/5" written here on 2026-09-08 never matched that
table; corrected 2026-09-14.* Every local run exposes the host's credentials to
the agent.

**Proposed solution:** Investigate `unshare` (Linux) or `sandbox-exec`
(macOS) for lightweight local isolation without Docker. Alternatively,
document that Docker is required for credential-sensitive projects.

**Verification:** S1–S4 pass on local provider, or explicit documented
decision that Docker-only is acceptable.

The original priority block, kept verbatim:

> **Priority:** P1 — security gap, even if honestly documented.
> **Effort:** Medium (OS-specific sandboxing is non-trivial).
> **Risk:** macOS `sandbox-exec` is deprecated; Linux `unshare` needs root.
> **Release target:** v1.2.0

**Status: CLOSED by decision, 2026-09-13** — the second branch of the
verification, taken twice. [ADR-006 §5](ADR-006-v1-exit-condition-reconciliation.md)
(2026-09-08) already ruled Local's lack of isolation a documented known
limitation rather than a blocked feature; [ADR-011](ADR-011-sandbox-local-provider.md)
(ACCEPTED 2026-09-13) closes it explicitly: **no isolation layer will be built
for `local`** — sensitive projects run Docker. Its lead argument is that a
half-working sandbox would have to declare `network_none: native` where it only
blocks half, and "declare capabilities honestly" is the most expensive
invariant in this repo.

**Priority (revised 2026-09-14):** none — closed, superseded by ADR-011. The two
risks the original block named are exactly the reasons ADR-011 gives for not
building it, so this item did not go stale so much as get answered.

---

## 3. OpenCode + Serena write-scope interop — **closed for the known tools, open as a class** (corrected 2026-09-14)

**Original problem (2026-09-08):** OpenCode's Serena plugin writes
`.serena/.gitignore`, `.serena/project.yml` into worktrees. These are outside
stories' declared `write_scope`, so the harness correctly rejects the
candidate.

**Original evidence:** Dogfood par-opencode run — all 3 stories failed because
of this. The harness behavior is correct; the agent ecosystem is the issue.

The original proposal, kept verbatim because the correction below refers to it:

> **Proposed solution:** Options:
>   (a) Auto-add `.serena/**` to `write_scope` when client is OpenCode.
>   (b) Add a `write_scope_ignore` config to exclude infrastructure files.
>   (c) Document as agent-side limitation; wait for Serena fix.
>
> **Verification:** OpenCode dogfood run completes with stories passing.
>
> **Priority:** P1 — blocks OpenCode from completing dogfood runs.
> **Effort:** Low (option a or b is a few lines).
> **Risk:** Option (a) is client-specific special-casing; option (b) is generic
> but might mask real scope violations.
> **Release target:** v1.1.0

**What actually shipped** — none of (a), (b) or (c). `.serena` (alongside
`.opencode`, `.claude/settings.json`, `.aisef`, the named `_bmad-output/…`
subpaths the harness itself writes, plus `VENDOR_PATHS`) went into the
`HARNESS_OWNED` tuple in
`aisef/harness/guardrails.py`, which every path that reads the candidate diff
shares (`changed_files`, and the `diff-scope` guard via
`HARNESS_OWNED + baseline_dirty_from_env(env)`). Landed in `ea4d035`
("fix: an MCP server's own notes killed a story", 2026-09-09), released in
v1.3.0:

```
git log --oneline -S'".serena"' -- aisef/harness/guardrails.py   # → ea4d035
git tag --contains ea4d035 | sort -V | head -1                  # → v1.3.0
```

**The "blocks OpenCode from completing dogfood runs" claim is now false.** On
2026-09-14 `todo-oc` — an OpenCode project, MiniMax-M3 behind the `mycombo`
alias — merged **7 of 7** stories:

```
python3 -c "import json;d=json.load(open('/Users/nghinh/Downloads/projects/todo-oc/_bmad-output/sprint-status.json'))['stories'];print(len(d), sorted({s['status'] for s in d.values()}))"
# → 7 ['done']
grep -ci serena /Users/nghinh/Downloads/projects/todo-oc/_bmad-output/run.log   # → 0
```

Zero `serena` and zero `write_scope` lines in a 163 KB run log across seven
stories. Written up in [DOGFOOD-2026-09-13 §8](DOGFOOD-2026-09-13.md#8-todo-oc-7-of-7--and-why-section-7-named-the-wrong-culprit).

**What still stands.** `HARNESS_OWNED` is a hard-coded inventory of tools the
framework happens to know about, and there is no config escape hatch —
`grep -rn 'write_scope_ignore' aisef/` returns nothing. So the *class* of
failure is not closed: the next MCP server or agent plugin that writes
somewhere outside that tuple kills a story the same way Serena did on
`todo-e2e` 2026-09-09, and the only fix is another commit to the framework.
Whether that is worth a config key is **undecided, and no decision record
exists either way** — the only thing written down is the Risk line in the quoted
proposal above ("option (b) is generic but might mask real scope violations"),
stated as a risk at proposal time, not as a rejection. Nothing has measured it
since.

**Verification for the part that remains:** a story completes on a project
whose agent runs a write-happy tool that is *not* in `HARNESS_OWNED`, without
editing `aisef/`. Not yet measured — no such run exists on disk.

**Priority (revised 2026-09-14):** P3 — no longer blocking anything measured;
reopen if a third tool costs a story.
**Effort:** Low (a knob) but the design question is the expensive part.
**Release target:** none scheduled.

---

## 4. Harder benchmark / challenge set

**Problem:** Current bench suite is **30** bug-fix tasks (28 valid) from a
single project (the framework itself). Not diverse enough to make strong
claims. *Said "15+" when written 2026-09-08; recounted 2026-09-14.*

**Evidence:** Bench report v0.3.0 — 96 runs, but all Python, all on aisef —
and the A-2 additions did not change that: all 30 task manifests carry
`"source": "bug"` and a `verify` command of the form
`python3 -m unittest -v tests.test_*`.

```
ls -d tests/bench/tasks/*/ | wc -l   # → 30
python3 -c "import json,pathlib,collections;print(collections.Counter(json.loads(p.read_text())['source'] for p in pathlib.Path('tests/bench/tasks').glob('*/task.json')))"
# → Counter({'bug': 30})
```

So of the three verification bars below, only the task count is met: **1
language, 1 source project, 30 tasks**.

**Proposed solution:** Add tasks from:
  - Different languages (JavaScript/TypeScript via par, Go, Rust)
  - Different task types (feature addition, refactoring, security fix)
  - External open-source repos with known-good fixes as ground truth

**Verification:** Bench suite covers >= 3 languages, >= 3 task types, >= 30
tasks.

**Priority:** P2 — improves evidence quality, not blocking anything.
**Effort:** Medium (curating good tasks takes judgment).
**Risk:** Ground-truth quality; tasks that are too easy or too hard.
**Release target:** v1.2.0

---

## 5. Distributed execution

**Problem:** Single-machine only. No multi-machine orchestration for large
projects with many epics.

**Evidence:** ADR-006 §3 deferred this. `worktree.py` has the merge lock
primitive but no cross-machine coordination.

**Proposed solution:** Define a coordination protocol (queue + lock service),
implement worker nodes that pull stories from the queue.

**Verification:** 2 machines, 1 epic, state merges correctly, no conflicts.

**Priority:** P3 — no user has asked for this; single-machine handles all
current workloads.
**Effort:** High (distributed systems correctness is hard).
**Risk:** Over-engineering without real demand.
**Release target:** v2.0.0 (if ever demanded)

---

## 6. Reliability / maintenance

**Problem:** No production telemetry. Bug reports come from dogfood and tests.

**Evidence:** 42 bugs found during dogfood as of 2026-09-08 (documented in
DEEP-REVIEW). Recounted 2026-09-14: [FAILURE-TAXONOMY](FAILURE-TAXONOMY.md)
now carries **124 rows numbered 22–147** (26 and 27 are absent), on top of bugs
1–21 in [STATUS-2026-09-05 §2.4](STATUS-2026-09-05.md) — every one of them
found by running, none by reading code.

```
grep -oE '^\| *[0-9]+ *\|' docs/FAILURE-TAXONOMY.md | tr -dc '0-9\n' | sort -n | uniq | wc -l   # → 124
```

Framework is stable but untested at scale.

**Proposed solution:** Track issues from external users (item 1). Fix based
on real reports, not speculative cleanup.

**Verification:** Issue tracker active, mean time to fix < 1 week for P0/P1.

**Priority:** P2 — becomes P0 once external users exist.
**Effort:** Ongoing, low per-issue.
**Risk:** No users = no reports = false sense of stability.
**Release target:** Continuous

---

## Non-goals

- **Large refactors** without evidence of friction.
- **Version bumps** for the sake of progress.
- **New features** not driven by user feedback or evidence.
- **Config key reduction** — already at 0 mandatory, **69** total with defaults
  (`python3 -c "from aisef.config import DEFAULTS; print(len(DEFAULTS))"` →
  `69`, measured 2026-09-14).

  *This number has now drifted twice, and the second time is instructive.  The
  line said 58 until `735f50f` (2026-09-14 06:00) measured 68; four minutes
  later `9244229` (06:04) added `story.verified_touched_weight` for ADR-009 O3
  from a parallel worktree, making it 69 — so the freshly measured figure was
  stale before it was committed.  The guarded copy is
  [`STABILITY.md`](STABILITY.md) § Config keys, pinned to
  `len(DEFAULTS)` by
  `tests/test_meta.py::TestConSoTrongTaiLieuKhopNguonDocDuoc.test_so_khoa_cau_hinh_trong_stability_khop_defaults`.
  Read the count there; this line is a copy and copies drift.*

## Lessons from MiMo-Code (2026-09-12)

[ADR-010](ADR-010-mimo-code-lessons.md) records a study of
[MiMo-Code](https://github.com/XiaomiMiMo/MiMo-Code) — an OpenCode fork with
persistent memory, `/dream` consolidation, `/distill` skill extraction, a
QuickJS tool-batching sandbox and a harness hand-off mechanism.

Three things landed: rate limits are no longer retried instantly, the retry
delay is read from what the provider says, and a ranking harness now exists for
memory retrieval. The ranking harness is the interesting one — it was built to
justify replacing AISEF's word-overlap scorer with BM25 and instead showed no
winner across two deliberately opposed datasets, so nothing was replaced.

Four candidates carry written measurement conditions and are not enabled:
evidence-backed memory consolidation, in-session stall detection, batched tool
execution, and MiMo as a third client (which stays closed until a memory
isolation test proves a fresh story cannot inherit a previous session's state).

Rejected with evidence from MiMo's own issue tracker: automatic checkpoints and
session resume (keep-alive loops, OOM at 6–20 GB), cross-tool transcript
ingestion, and a second canonical task state.


## Re-check trigger: `phases/implement.py` (2026-09-12)

The file was 2 581 lines when this trigger was written (verified:
`git show a899fa0:aisef/phases/implement.py | wc -l` → 2581). **2 877 lines on
2026-09-14** (`wc -l aisef/phases/implement.py`) — +296 across 15 commits
(`git log --oneline a899fa0..HEAD -- aisef/phases/implement.py | wc -l`),
the turn-cap grading fix and the plan-deadlock detectors among them. By this
project's own splitting rule
— split on evidence of real friction, not on a line count — **not splitting is
still correct**: none of those bugs was caused by the file's size, and a split
would move code without fixing anything. The threshold to watch remains the one
already set: three consecutive bugs concentrated in this file.

Splitting is not free either, so the decision gets a trigger rather than a
re-argument every release:

> If **three consecutive real bugs** land in `aisef/phases/implement.py`, split
> it — and split along the seam the three bugs share, not along a tidy one.

Bugs are counted from the numbered bug log in `CHANGELOG.md`. Three bugs in one
file is the point where "the file is fine" stops being a claim about evidence
and starts being a habit.
