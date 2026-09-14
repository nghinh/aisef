# Docs truth pass — 2026-09-14

A pass over this project's own documentation looking for drift between what the
docs assert and what the code, git history and dogfood evidence on disk
actually say. Worktree branch `worktree-agent-aefff4d5d4a4eff6c`, base
`b26d068`.

Every number below came from a command run in this session; each row quotes it.
Where a doc asserted something I could neither confirm nor refute, it is marked
unverified in the doc with the measurement that would settle it, and listed in
§3 here.

**Suite state:** `ruff check .` → `All checks passed!`; `python3 -m pytest -q` →
`2523 passed, 80 skipped, 1062 subtests passed in 295.48s` (exit 0). The new
meta-test is inside that count.

---

## 1. The three drifts I was pointed at

### D1 — `ROADMAP-POST-1.0.md` item 3: "blocks OpenCode from completing dogfood runs"

**Status: confirmed false. Rewritten, keeping the part that still stands.**

Proof:

```
python3 -c "import json;d=json.load(open('/Users/nghinh/Downloads/projects/todo-oc/_bmad-output/sprint-status.json'))['stories'];print(len(d), sorted({s['status'] for s in d.values()}))"
# → 7 ['done']
grep -ci serena     /Users/nghinh/Downloads/projects/todo-oc/_bmad-output/run.log   # → 0
grep -ci write_scope /Users/nghinh/Downloads/projects/todo-oc/_bmad-output/run.log  # → 0
git log --oneline -S'".serena"' -- aisef/harness/guardrails.py                      # → ea4d035
git log -1 --format='%ad' --date=short ea4d035                                      # → 2026-09-09
git tag --contains ea4d035 | sort -V | head -1                                      # → v1.3.0
grep -rn 'write_scope_ignore' aisef/                                                # → (nothing)
```

Seven of seven stories `done`, zero `serena` and zero `write_scope` lines in a
163 KB run log. The fix landed 2026-09-09 in `ea4d035`, released in v1.3.0 —
and it was **none of the three options the roadmap listed**: `.serena` went into
the hard-coded `HARNESS_OWNED` tuple in `aisef/harness/guardrails.py`, which
`changed_files` and the `diff-scope` guard both read.

**What still stands, and is now written as the open part:** `HARNESS_OWNED` is
an inventory of tools the framework happens to know about, with no config
escape hatch (`write_scope_ignore` does not exist anywhere in `aisef/`). The
*class* of failure — an agent-side tool writing outside every story's scope — is
not closed; the next unknown MCP server costs a story and a framework commit.
Item re-priced P1 → P3, with a verification that is honestly marked as not yet
measured (no run on disk exercises a write-happy tool outside the tuple).

### D2 — `DANH-GIA-360-2026-09-12.md` counts

**Status: confirmed stale on every number named, and on three more. Refreshed
with a dated §10 rather than marked historical.**

**Why that choice** (asked for explicitly): the document is not dormant. §5
carries inline `✅ 13/09` marks, and §8/§9 are its own dated execution logs.
More decisively, it already contradicts itself — §6's tracking table says
"Commit chưa phát hành: **0**" while §1 and §3.7 still say "61 commit chưa
phát hành". Marking the whole file historical would bury §8/§9, the only place
recording what happened *after* the assessment. So: a warning box after the
header pointing at §10, the old numbers left untouched in place as the record of
the 12/09 session, and a new §10 that recounts with commands.

| Doc said (12/09, `a899fa0`) | Measured 14/09 (`b26d068`) | Command |
|---|---|---|
| latest release `v1.2.31` | **`v1.5.0`** (2026-09-13) | `git tag \| sort -V \| tail -1` |
| 61 unreleased commits | **33** since `v1.5.0` | `git rev-list --count v1.5.0..master` |
| 63 bugs | **124 rows, ids 22–147** (26, 27 absent) + bugs 1–21 elsewhere | `grep -oE '^\| *[0-9]+ *\|' docs/FAILURE-TAXONOMY.md \| tr -dc '0-9\n' \| sort -n \| uniq \| wc -l` → 124 |
| 2 276 tests | **2 523 passed, 80 skipped, 1 062 subtests** | `python3 -m pytest -q` → `2523 passed, 80 skipped, 1062 subtests passed in 295.48s` |
| 28 682 framework lines | **30 708** | `find aisef -name '*.py' \| xargs wc -l \| tail -1` |
| 27 899 test lines | **33 333** | `find tests -name '*.py' \| xargs wc -l \| tail -1` |
| 31 CLI commands | **32** | `python3 -m aisef.cli --help`, count entries in `{…}` |
| 9 guards | **10** (`tool-bypass` added) | `python3 -c "from aisef.harness.guardrails import GUARD_MATCHERS; print(len(GUARD_MATCHERS))"` |
| `implement.py` 2 581 lines | **2 877** | `wc -l aisef/phases/implement.py` |
| docs: 40 files, ~119 000 words | **48 `.md`, 162 181 words** | `ls docs/*.md \| wc -l` · `cat docs/*.md \| wc -w` |
| §3.6 "no lint gate for the framework" | **exists and green** | `ruff check .` → `All checks passed!`; job `lint` in `.github/workflows/tests.yml` |
| 68 config keys | **68** — unchanged | `python3 -c "from aisef.config import DEFAULTS; print(len(DEFAULTS))"` |
| 16 gate checks | **16** — unchanged | `python3 -c "from aisef.control.gate import CHECK_NAMES; print(len(CHECK_NAMES))"` |
| 30 bench tasks (28 valid) | **30 (28 valid)** — unchanged, still 1 language / 1 source project | `ls -d tests/bench/tasks/*/ \| wc -l`; every `task.json` has `"source": "bug"` |
| 0 external users | **0** — nothing on disk says otherwise | `EXTERNAL-VALIDATION-v1.1.0.md` is still a protocol with unticked `- [ ]` boxes |

§10 also reconciles §4's P0/P1 list against what closed (release, ADR-009 §Open,
ADR-011, lint gate) and what did not (B-3 frontier bench, external user), and
adds the partial answer to §1's central question that did not exist on 12/09:
the AISEF-vs-bare delta **changed sign** between C-1 (−0,06, n=3) and C-1b
(+0,06, n=6), which C-1b itself reads as noise.

**A note on measurement hygiene, recorded in §10.** My first full suite run gave
`1 failed, 2521 passed` — `tests/test_clients.py::TestTranLuotDoAdapterThiHanh::test_cham_tran_thi_dung_tien_trinh_va_goi_ten_dung`.
Run alone: `1 passed in 0.53s`. The machine was carrying five parallel agents —
this repo's own bug 22 and operational lesson 5. Not a code defect; recorded in
§10 so the next reader measures load before concluding.

### D3 — the ADR-009 rule: *"a statement of the form 'N items remain' must carry the list, on disk, in the same document"*

Swept `docs/` for statements of that shape:

```
grep -rnE '[0-9]+ (remaining|more|other|further) (stor|issue|item|bug|gap|task|check|thing|problem|defect)' docs/*.md
grep -rnE '(còn|còn lại|chưa)[^.]{0,30}\*{0,2}[0-9]+\*{0,2} (vấn đề|mục|lỗi|story|gap|task|cái|thứ|việc)' docs/*.md
```

Five hits of the right shape (after discarding matches that were about a gate's
internals, a paper's figures, or a run-time observation log rather than project
state). Verdicts:

| Where | Carries its list? | What I did |
|---|---|---|
| `ADR-009 § Open` — "the four remaining semantic issues" | **yes** — O1–O4, each with its measurement | nothing (and O1–O4 were off-limits) |
| `ROADMAP-POST-1.0.md § Cross-tier invariants` — "the other four issues are semantic" | **yes** — names all four inline and links the ADR anchor | nothing |
| `V1-READINESS.md` B3 — "4 remaining stories need real agent runs" | **no** — the count was there, the names were not | added the list: STORY-01-04, 01-05, 01-06, 01-07 (the names were already on disk in `EXECUTION-PLAN.md` R2, just not in this file). Historical doc, already labelled COMPLETED — annotated, not rewritten |
| `ADR-004` §B1 — "còn 15 gap" | **no, and cannot** | added a dated annotation saying so. The list lived in `e9/_bmad-output/ledger.json`; `ls -d /Users/nghinh/Downloads/projects/e9` → no such directory. Marked **unverifiable** with the measurement that would settle it (re-run e9 EPIC-01, then `aisef issues`) and the note that it costs real money and answers no open question |
| `ADR-010` — "phần còn lại là PROPOSED" | **yes** — the fit/gap matrix in the same file labels every item | nothing |

---

## 2. Drift I found on my own

### D4 — `STABILITY.md` says 9 guards; `GUARD_MATCHERS` has 10

```
python3 -c "from aisef.harness.guardrails import GUARD_MATCHERS; print(len(GUARD_MATCHERS), sorted(GUARD_MATCHERS))"
# → 10 ['completion','destructive','diff-scope','egress','git-stage','injection','process-ref','secret','tool-bypass','write-scope']
grep -n '### Guards' docs/STABILITY.md    # → "### Guards (9 guards)"
```

`tool-bypass` was missing from both the count and the table — in a **frozen API
contract** document, and directly below the config-key count that a meta-test
already guards. README already said "ten guards", SOLUTION.md §834 said 10, so
STABILITY.md was the only one wrong.

Fixed the heading and added the missing row. Also added
`TestConSoTrongTaiLieuKhopNguonDocDuoc.test_so_guard_trong_stability_khop_matchers`
— the same wiring the project built on 12/09 for the config-key count, which
stopped one line short. Negative control run both ways before accepting it:
reverting the count to 9 → red; deleting the `tool-bypass` row → red.

### D5 — `FAILURE-TAXONOMY.md` opens with "Bốn mươi bảy lỗi" (47) over a table of 147

The section heading (`## Lỗi 22–147`) is meta-test-guarded and was correct; the
intro paragraph above it was not guarded and still described a 47-bug document
covering 2026-09-05 → 09. Replaced with the measured count (124 rows, 22–147,
26/27 absent) and a date band table derived from commit dates rather than
guessed:

```
git log --format=%ad --date=short -S'| N |' -- docs/FAILURE-TAXONOMY.md | tail -1
# 22→06/09 · 32→09/09 · 64→10/09 · 71→12/09 · 76→13/09 · 142→14/09
```

I wrote a first version of that table from memory and the boundaries were wrong
(48 landed 09/09, not 10/09; 87 landed 13/09, not 12/09) — the scan above is
what produced the version in the file.

### D6 — `ROADMAP-POST-1.0.md` item 2 evidence: "Local 1/5"

```
grep -A8 'Phép thử' docs/SANDBOX-CONFORMANCE.md
# S1 ✗ · S2 ✗ · S3 ✅ · S4 ✗ · S5 ✅  →  local 2/5, docker 5/5
```

The roadmap's own cited table has always said 2/5. Corrected, with the
correction dated and stated rather than silently swapped.

### D7 — `ROADMAP-POST-1.0.md` item 2 was decided twice and the roadmap says neither

`ADR-011-sandbox-local-provider.md` — "Ngày: 2026-09-13. Trạng thái:
**ACCEPTED**. Thay cho mục S1 còn treo" — closes it: no isolation layer for
`local`, Docker for sensitive projects. `ADR-006 §5` (2026-09-08) had already
ruled it a documented known limitation. Item 2 still read as open P1 research
work with `unshare`/`sandbox-exec` to investigate. Marked CLOSED by decision
with both ADRs cited.

### D8 — `ROADMAP-POST-1.0.md` memory paragraph reads as an open research queue

`ADR-007 § Addendum — frozen (2026-09-12)` moved memory from *EXPERIMENTAL,
default OFF* to **FROZEN, default OFF** — explicitly "no new capability". The
roadmap's lead paragraph still listed four pending enablement items as if
scheduled. Added a dated status correction quoting the thaw condition; left the
original paragraph in place as the record.

### D9 — `ROADMAP-POST-1.0.md` stale counts: 58 config keys, 15+ bench tasks, 42 bugs, 2 581 lines

- "58 total with defaults" → 68 (`len(DEFAULTS)`). Same number the 12/09 pass
  fixed in STABILITY.md; the roadmap copy was missed.
- "15+ bug-fix tasks" → 30. And I made the *unchanged* part explicit, because
  it matters more than the count: all 30 `task.json` carry `"source": "bug"`,
  so of item 4's three bars (≥3 languages, ≥3 task types, ≥30 tasks) only the
  task count is met.
- "42 bugs found during dogfood" → kept as the dated 2026-09-08 figure, with
  the recount beside it.
- `implement.py` "2 581 lines" → 2 877. Verified the old number was right when
  written (`git show a899fa0:aisef/phases/implement.py | wc -l` → 2581) and that
  the growth is 15 commits, so the re-check trigger's conclusion ("not
  splitting is still correct") survives rather than being asserted.

### D10 — `EXECUTION-PLAN.md` bench queue: C-1 still shown as running

The queue table said C-1 was "🔄 chạy 12/09 19:10 → 13/09, 11/12 task xong,
`multi-4` đang chạy". `docs/BENCH-REPORT-C1.md` and `docs/BENCH-REPORT-C1B.md`
both exist and are closed reports. Marked ✅ with the closing figures, C-1b
added, and — separately — the queue's "Thứ tự thực thi: **B-3 → C-1 → C-2 →
C-3**" split into planned order vs **actual** order (C-1 → C-1b → C-2, B-3 never
run), with the reason already on disk in DANH-GIA-360 (no Anthropic credential
in this environment) cited rather than left as an unexplained discrepancy.

### D11 — `BENCH-REPORT-v1.3.md` § Status: "Next in line: B-3, then C-1"

Both C-1 and C-1b ran; B-3 is the only one that did not. Corrected, and the
partial answer added — including that the delta changed sign, quoted from C-1b
rather than editorialised. Also annotated `aisef/clients/simulated.py` in §7,
which was the correct path on 12/09 and moved to `tests/bench/simulated.py`
later the same day.

### D12 — `ADR-009 § Deferred`: flock stress test "documented but not implemented"

```
ls tests/test_lease_stress.py                       # → exists
grep -n 'Popen\|def test' tests/test_lease_stress.py # → subprocess.Popen × SO_CON, 2 tests
```

The file's own docstring cites this ADR's deferral. Struck the bullet through
and replaced with what was actually done, keeping the part that remains
unmeasured (cross-UID `flock` semantics — the test covers same-UID only, which
is what the bullet asked for). This is in §Deferred, not in O1–O4.

### D13 — `HUONG-DAN-SU-DUNG.md`: "sẽ có ở bản kế" three releases later

```
D=/tmp/initprobe; rm -rf $D; mkdir -p $D
python3 -m aisef.cli --project $D init --stack python
python3 -c "import json;d=json.load(open('$D/.ai/config.json'));print(len(d), sorted(d))"
# → 4 ['sandbox.allow_hosts', 'sandbox.image', 'tools.lint', 'tools.test']
```

The Vietnamese guide said 1.3.0 wrote all 68 defaults and the fix "sẽ có ở bản
kế" (will land in the next release). v1.3.1, v1.4.0 and v1.5.0 have shipped
since. The **English twin (`USAGE-GUIDE.md` line 156) was already correct**
("1.3.1 does not") — the drift is one-sided, which is the interesting part: the
two guides are maintained separately and only one got the follow-up. Corrected
with the probe above, and I re-measured on 1.5.0 rather than trusting the
English twin.

---

## 3. Found and deliberately left alone

| Thing | Why left |
|---|---|
| `V1-READINESS.md` A7 "58 keys" / A8 "9 guards" | Correct record of 2026-09-08, in a document whose header already says "**COMPLETED.** … retained as historical record". Rewriting these would falsify the checklist. Only B3's missing list was added, because the ADR-009 rule is about being able to audit a claim, not about the number |
| `V1-READINESS.md` B1 "last run 2026-09-06, expires 2026-09-20" | *Added by the second pass, 2026-09-14.* Same class as A7/A8, and checked rather than assumed: `git show 8095d9a^:docs/CONFORMANCE.md` shows the table said **2026-09-06** when the row was authored (08:37), and `af827f4` refreshed it to 2026-09-08 at 12:21 the same day. The row was true when written; the real expiry is 2026-09-22. Annotated in place with that date, not rewritten |
| `RELEASE-CHECKLIST-v0.1.0.md` / `RELEASE-PLAN-v0.1.0.md` "S1 blocked" | v0.1.0 release records. True when written; ADR-011 supersedes the *decision*, not the record. The live document (ROADMAP item 2) is where the correction belongs, and that is where I put it |
| `DANH-GIA-360-VA-LO-TRINH.md` (dangling `docs/BENCHMARK.md`) | Already labelled historical by its successor's header. Superseded docs keep their dead links here |
| `FAILURE-TAXONOMY.md` cause-class table stops at bug 47 | Real gap — the class table's example column was never extended past 47. Filling it means re-reading ~100 rows and fixes nothing: **column 2 of the bug table already declares each bug's class**, on every row. Labelled in the doc as a selection of examples rather than an index, which is what it is |
| `BENCH-OBSERVATIONS-C1.md` "Năm task còn lại quyết định" | An observation log written *during* the run. `BENCH-REPORT-C1.md` states as policy that observations are not corrected after the fact, including ones later shown wrong. Correcting it would break that invariant, which is worth more than the consistency |
| `BENCH-REPORT-v1.3.md` §3 simulator numbers | §7 already says historical numbers are preserved, not regenerated. Left alone by design |
| `BENCH-REPORT-v1.3.md` §6.5 `tests/tester_simulated.py` | Never existed in this repo — it reads as a "-style" pointer at an external harness pattern inside a future-work list, not a claim that the file is here. Could not confirm either reading from disk; left, and flagged here rather than guessed at |
| `ADR-009` O1–O4 | Off-limits by instruction (four agents working there). Only cross-references to them were touched, and the anchors are meta-test-verified |
| `CHANGELOG.md`, `README.md`, `README.vi.md` | Off-limits by instruction. **README/README.vi bug counts are meta-test-guarded against `max(bug ids)` = 147, so they are already correct.** No unguarded drift found in them |

---

## 4. Unverified, with the measurement that would settle it

1. **PyPI really serves 1.5.0.** `pyproject.toml` says `version = "1.5.0"` and
   tag `v1.5.0` exists; releases go out by trusted publishing on tag, so the
   inference is strong — but I did not reach the network. Settle with
   `pip index versions aisef` or `pip install aisef==1.5.0` in a clean venv.
   §10 states the release as the tag, not as a PyPI fact.
2. **The 15 e9 gaps** (D3). The evidence tree is gone; only a paid re-run
   settles it. Written into ADR-004 as unverifiable rather than repeated as
   fact.
3. **`todo-oc` ran through OpenCode.** Strongly supported — a `.opencode/`
   directory in the project, `ses_…` session ids in
   `_bmad-output/evidence/*.jsonl`, and DOGFOOD-2026-09-13 states it — but the
   run log does not record a `client=` line. Settle by adding the client name to
   the `pipeline START` line in `run.log`, which would be worth doing anyway:
   the single most load-bearing fact about a run is not in its own log.

   **Settled for future runs, 2026-09-14** (`0957ddb`). Both start lines now
   carry the client:

   ```
   grep -n 'pipeline START' aisef/phases/plan.py
   # → _run_log(project, f"pipeline START client={getattr(client, 'id', '') or '?'}")
   grep -n 'sprint START' aisef/phases/run.py
   # → run_log(artifact_root, f"sprint START client={client.id} "
   ```

   **It does not settle the item as asked, and that is the point.** The fix is
   forward-only: no existing corpus gains a `client=` line, so which client
   produced `todo-oc`, `todo-cli`, `todo` or `todo-e2e` is still an inference
   from `.opencode/` directories and session-id shapes, not a record. An
   unverified claim about the past closes by re-running or not at all; what a
   harness fix buys is that the *next* reader never has to ask. The same
   asymmetry applies to the client/model split in
   [`o1-reviewer-qualification.md` § How ground truth is derived, item 5](o1-reviewer-qualification.md) — same
   commit, same forward-only reach.

---

## 5. Gate state in this worktree

```
ruff check .          # → All checks passed!
python3 -m pytest -q  # → 2523 passed, 80 skipped, 1062 subtests passed in 295.48s
```

The new meta-test is included in that count. Nothing was weakened to pass.

---

## Paragraph for CHANGELOG.md

> **Docs truth pass (2026-09-14).** Thirteen drifts between the documentation and
> what the code, git history and dogfood evidence actually say, each proved by a
> quoted command. The headline correction: `ROADMAP-POST-1.0.md` claimed the
> OpenCode/Serena write-scope interop "blocks OpenCode from completing dogfood
> runs" — `todo-oc` merged 7 of 7 stories through OpenCode on 2026-09-14, and
> the fix had shipped in v1.3.0 (`.serena` in `HARNESS_OWNED`, `ea4d035`); the
> item now records what closed and the part that genuinely remains open (no
> config escape hatch, so an unknown agent-side tool still costs a story).
> `docs/STABILITY.md` declared 9 guards against 10 in `GUARD_MATCHERS` —
> `tool-bypass` was missing from a frozen API contract, now fixed and wired to a
> meta-test with a negative control, the same wiring the 12/09 pass gave the
> config-key count one line above. `ROADMAP-POST-1.0.md` item 2 was closed twice
> on disk (ADR-006 §5, ADR-011) while still reading as open P1 research, and its
> cited sandbox evidence said "Local 1/5" where the table it cites says 2/5.
> `DANH-GIA-360-2026-09-12.md` gets a dated §10 recount rather than a historical
> label, because it was contradicting itself (§6 said 0 unreleased commits, §1
> said 61) and marking it historical would bury its own execution logs: latest
> release `v1.2.31`→`v1.5.0`, 61→33 unreleased commits, 63→147 bugs,
> 2 276→2 523 tests, 9→10 guards, `implement.py` 2 581→2 877 lines.
> `FAILURE-TAXONOMY.md` opened with "forty-seven bugs" above a table of 147, and
> its date bands are now read from commit dates instead of prose.
> `EXECUTION-PLAN.md` still showed cohort C-1 mid-run and the bench queue in an
> order it was not executed in; `BENCH-REPORT-v1.3.md` still pointed at C-1 as
> "next in line". Under ADR-009's rule that "a statement of the form 'N items
> remain' must carry the list, on disk, in the same document", four statements of
> that shape were audited: two already carried their lists, `V1-READINESS.md` B3
> got its four story ids, and ADR-004's "còn 15 gap" is now marked
> **unverifiable** — the e9 evidence tree no longer exists on disk — with the
> measurement that would settle it, rather than repeated as fact. Superseded
> records were annotated and dated, never rewritten.
