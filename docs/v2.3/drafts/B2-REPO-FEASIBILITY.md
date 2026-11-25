# B2 — External repository slate: feasibility research (read-only)

**Date:** 2026-11-26
**Status:** RESEARCH INPUT to the B2-SPEND decision package (protocol draft §5.1, §9.3). This file confers
**no approval and commits no spend**. Selecting any repo into the corpus is the owner's B2-SPEND decision
(protocol §2.3 last ¶, §5.1); the ≤ 08/12 decision date (protocol §5.2) is the deadline this research feeds.
**Method:** read-only web research only (GitHub REST API + repo pages, 2026-11-26). Nothing was cloned,
downloaded, or executed; no account was created; no one was contacted. Everything that requires a local
checkout is explicitly deferred to the §2.3 clone-time checks (see §5 below), which the protocol already
permits without a spend entry ("read-only cloning of public repos for *feasibility checks* under §2.3" —
protocol §5.1).

---

## 1. Criteria applied (from `B2-GROUND-TRUTH-PROTOCOL-DRAFT.md`)

| # | Criterion | Source | Checkable read-only? |
|---|---|---|---|
| C1 | 1,000–200,000 lines in the primary language at the pinned SHA | §2.3(1) | **Estimate only** (repo size + file layout); exact count needs the clone |
| C2 | Clean checkout builds + test suite green on Linux **and** macOS, offline, < 10 min | §2.3(2) | **Partially** — CI matrices show which OSes are exercised; green-offline-<10min needs the clone |
| C3 | Acceptance criteria expressible with the shipped probe catalog (CLI / Python callable / process effect / file artifact), verified by running one | §2.3(3) | **Assessed, not verified** — behavior surface judged from docs; the one-criterion run needs the clone |
| C4 | OSI-approved license permitting local modification and analysis | §2.3(4) | **Yes** (SPDX id from the GitHub API) |
| C5 | Independence: appears nowhere in AISEF history (no dogfood, fixture, workload record); shares no workload-identity component with LedgerLock or a sealed cohort; not AISEF / todo-oc / todo-cli | §2.3(5), §2.5 | **Yes** — `git grep -il <name>` over the whole AISEF tree run 2026-11-26 (see §1.1) |
| C6 | Pinnable: commit SHA at a release tag; archive sha256 recorded | §2.3(6) | **SHA yes** (tags API); archive sha256 needs the download |
| C7 | Slate SHOULD span ≥ 2 primary languages and ≥ 2 harness styles | §2.3 last ¶ | Yes (see §6 — the language SHOULD is NOT met by this slate) |
| C8 | Representative for an SDLC-from-requirements evaluation: documented behavior crisp enough for independent ground-truth labels; a seedable defect surface per §2.2/§2.4 | §2.2, §2.4, §3.1 | Assessed from docs/README/spec |

### 1.1 Independence check (C5) — result

`git grep -il` for every candidate name over the AISEF tree (code, tests, fixtures, closure-evidence, docs)
on 2026-11-26: **no candidate appears as a dependency, fixture, or workload** (`pyproject.toml`
`dependencies = []` — the framework is stdlib-only). Three string hits were inspected and are false
positives: the verb "tabulated" (`aisef/control/machine_gate.py:441`), the word "bottleneck"
(`docs/PROJECT-CLOSURE-GATE.md`, architecture matrix), and the unrelated **Go** module
`github.com/dustin/go-humanize` inside the round-5 OCR build's module graph (not python-humanize). None of
the candidates is AISEF, todo-oc, todo-cli, or LedgerLock-adjacent.

---

## 2. Candidate table (9 candidates, 4 domains)

All data from the GitHub API on 2026-11-26. "Size" is the API repo size plus a LOC estimate from the layout
— **C1 is confirmed only at clone time**. SHAs are the tag's commit SHA from the tags API.

| # | Repo | Domain | License (SPDX) | Lang | Stars | Size (est.) | Tests / how run | Pinned snapshot (tag → commit SHA) | Activity | Key risks |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | [kellyjonbrazil/jello](https://github.com/kellyjonbrazil/jello) | CLI utility (JSON/JSON-Lines filter, jq-like) | MIT | Python | 535 | 605 KB; ~3–5k LOC est. | stdlib `unittest`: `python -m unittest discover tests`; CI matrix **ubuntu + macos + windows** | `v1.6.1` → `b43c9b24605ce2fca7bb303cdd845f8e814c15fa` | last push 2025-05-30 | Slow cadence (~18 mo since last release); otherwise the cleanest CLI subject (stdlib-only runtime) |
| 2 | [lepture/mistune](https://github.com/lepture/mistune) | Parsing/format library (Markdown, CommonMark-compliant) | BSD-3-Clause | Python | 3,087 | 1.8 MB; ~10k LOC est. | pytest via uv: `uv run --locked --group test pytest`; CI **ubuntu only** | `v3.4.0` → `f19057fdf339affb61ca63c7fe28df7a951ec588` (release 2026-10-19) | active (push 2026-10-23) | macOS not CI-verified (pure Python, likely fine — C2 clone check decides); uv-locked toolchain to pin |
| 3 | [msiemens/tinydb](https://github.com/msiemens/tinydb) | Data tool (embedded document DB, pure Python) | MIT | Python | 7,584 | 1.3 MB; ~2k core LOC est. | pytest via uv: `uv run py.test --cov=tinydb`; CI matrix **ubuntu + macos + windows** | `v4.9.0` → `1e39ad3a2d9eca57efd9019fd089b5a04676da95` (release 2026-08-06) | active (push 2026-11-24) | Library-only surface (Python-callable + file-artifact probes, no CLI) |
| 4 | [bottlepy/bottle](https://github.com/bottlepy/bottle) | Small web/API framework (WSGI micro-framework) | MIT | Python | 8,804 | 6.7 MB; single file ~4.5k LOC + tests | pytest: `pytest -ra -q --cov=bottle`; CI **ubuntu only** | `0.13.4` → `b0a0a1014f7a7e6f6b7c193886a0913f46ee3ee6` (release 2025-06-15) | active (push 2026-10-25) | Single-file layout is atypical as a re-implementation target; some adapter tests bind local sockets (offline but process-effect-heavy); macOS not CI-verified |
| 5 | [simonw/sqlite-utils](https://github.com/simonw/sqlite-utils) | Data tool, CLI + library (SQLite manipulation) | Apache-2.0 | Python | 2,237 | 2.2 MB; ~10k core + large test suite est. | pytest: `pytest -v`; CI matrix **ubuntu + macos(×2) + windows** | `4.2.1` → `28dc6278cc03a9245325d056e6986818544abc68` (release 2026-08-13) | active (push 2026-11-12) | Larger; real dependency tree (click, tabulate, …); optional native bits (SpatiaLite, gcc test extension) are ubuntu-only and must be excluded from the harness |
| 6 | [astanin/python-tabulate](https://github.com/astanin/python-tabulate) | Format/output library + small CLI (table pretty-printer) | MIT | Python | 2,595 | 783 KB; ~2.5k core LOC est. | pytest/tox per repo docs (verify at clone) | `v0.10.0` → `3b4cd509820e4c45cd2aaba833aa585ea6308b94` | push 2026-03-11 | No GitHub Releases (tags only); slow cadence; it is a dependency of sqlite-utils — avoid pairing both in one slate |
| 7 | [python-humanize/humanize](https://github.com/python-humanize/humanize) | Small utility library (human-readable numbers/dates, i18n) | MIT | Python | 770 | 1.1 MB; ~3k LOC est. | pytest | `4.17.0` → `a95004512dde4e8f0269946bb4af754382347441` (release 2026-11-12) | active | Locale/gettext behavior varies by platform — labeling needs a pinned locale; narrow defect surface |
| 8 | [wireservice/csvkit](https://github.com/wireservice/csvkit) | Data CLI suite (CSV convert/inspect/query) | MIT | Python | 6,421 | 22 MB; ~5k LOC + heavy deps | pytest | `2.2.0` → `bdd6e7e25b52cb52073c1a19dd0210cd85894871` | active (push 2026-11-09) | Heavy dependency tree (agate, openpyxl, SQLAlchemy) threatens the offline + <10 min bar (C2); 22 MB repo |
| 9 | [python-poetry/tomlkit](https://github.com/python-poetry/tomlkit) | Parsing/format library (style-preserving TOML) | MIT | Python | 871 | 1.6 MB; ~6k LOC est. | pytest (toml-test spec fixtures) | `0.15.3` → `d2aa305673a01eafd0edda54ef07ebcb8902f4d4` (release 2026-11-24) | very active | Round-trip/style-preservation semantics are subtle — harder for evaluators to label than plain parse-correctness |

Domain coverage across candidates: CLI utility (1, 5, 8), parsing/format library (2, 6, 9), web/API tool
(4), data tool (3, 5, 8), small library (7) — ≥ 3 domains satisfied (C7 harness-style SHOULD).

---

## 3. Recommended top-3 slate

The slate optimizes for: all six §2.3 criteria plausibly passing at clone time, three distinct
domains/harness styles, probe-catalog fit (C3), crisp documented behavior for independent labels (C8), and
small enough bundles that seeding ≥ 9 items per repo (Q1) by 05/01 is realistic (§5.2 timeline).

### 3.1 jello `v1.6.1` @ `b43c9b24605ce2fca7bb303cdd845f8e814c15fa` — MIT — the CLI subject

A jq-like CLI that filters JSON with Python syntax: stdin/argument in, JSON out, exit codes documented. Its
runtime is stdlib-only and its tests are plain `unittest` with a 3-OS CI matrix including macOS — the
lowest-risk candidate for the offline Linux+macOS < 10 min bar (C2). Acceptance criteria map directly onto
the shipped probe catalog (CLI invocation with exact stdout/exit-code assertions; file artifacts via
output redirection), and the README + man-page behavior is concrete enough that two independent evaluators
can label SATISFIED/VIOLATED per criterion from the docs alone (C8). The defect surface (initialization
options, slicing semantics, schema/lines output modes, error handling on malformed JSON) seeds naturally
into P0–P3 classes. Known trade-off: last release 2025-05 — the project is stable rather than fast-moving;
since B2 measures a pinned snapshot, staleness costs nothing here, but it is recorded.

### 3.2 mistune `v3.4.0` @ `f19057fdf339affb61ca63c7fe28df7a951ec588` — BSD-3-Clause — the parsing subject

A pure-Python Markdown parser, fully CommonMark compliant. The CommonMark spec is an *external, frozen,
example-numbered* definition of correct behavior — the best possible substrate for independent ground-truth
labels: an evaluator can cite spec example N as the `basis` field (§3.1) without ever seeing the kernel or
the seeding recipes. Criteria are Python-callable probes (parse string → assert HTML) plus file-artifact
probes (render file). Seeding in/out-of-scope defects is clean: contract a subset of CommonMark constructs,
seed violations inside and outside the contracted subset — a direct fit for the §2.2 three-class
requirement. Active (release 2026-10). Risk: CI is ubuntu-only, so macOS green is asserted by purity, not
CI — the clone-time C2 check must confirm it; the uv-locked test route gives an exactly pinned toolchain.

### 3.3 tinydb `v4.9.0` @ `1e39ad3a2d9eca57efd9019fd089b5a04676da95` — MIT — the data subject

A pure-Python embedded document database (~2k core LOC) with excellent API documentation and a 3-OS CI
matrix. It brings the harness style the other two lack: stateful behavior with **file artifacts** (the JSON
storage file) plus Python-callable probes — insert/query/update semantics, caching middleware, and
persistence-format behavior are all documented and independently checkable. Requirements for an
SDLC-from-requirements evaluation write themselves ("a document store with X query operators, Y storage
format, Z middleware"), and seeded defects split naturally between contracted query semantics (in-scope)
and uncontracted extras like string-representation details (out-of-scope). Active (push 2026-11-24). Risk:
no CLI surface — acceptable because jello covers CLI-invocation probes; the slate still spans ≥ 2 harness
styles (C7).

**Slate-level check:** 3 repos, 3 domains (CLI / parsing library / data store), 2+ harness styles, licenses
MIT + BSD-3-Clause + MIT, all pure Python with no native dependencies, every snapshot pinned to a release
tag's commit SHA, independence verified against the AISEF tree (§1.1). Estimated combined LOC well inside
C1 bounds. The one §2.3 SHOULD not met: a single primary language — see §6.

---

## 4. Alternates

### 4.1 bottle `0.13.4` @ `b0a0a1014f7a7e6f6b7c193886a0913f46ee3ee6` — MIT — swap-in for the web/API domain

If the owner wants the web/file-artifact harness style represented explicitly (protocol §2.3 names
"web/file-artifact surface" as an example style), bottle is the strongest small candidate: an actively
maintained, MIT-licensed, single-file WSGI micro-framework (~4.5k LOC) whose routing/request/response
behavior is thoroughly documented and testable offline through WSGI process-effect probes (no external
network). It replaces tinydb or mistune at the owner's preference. It is ranked alternate, not top-3,
because the single-file architecture is an unusual shape for a re-implementation-from-requirements bundle,
some adapter tests exercise local sockets (more moving parts for the INDETERMINATE budget, §4.2 Q5), and
macOS is not CI-verified.

### 4.2 sqlite-utils `4.2.1` @ `28dc6278cc03a9245325d056e6986818544abc68` — Apache-2.0 — swap-in for CLI+data

A professionally maintained CLI **and** library for SQLite manipulation with a 48-job CI matrix across
Linux/macOS/Windows and an exemplary pytest suite — the richest acceptance-harness seed in the table, and
it covers two domains in one repo. It is ranked alternate because it is the largest candidate (slower
seeding, bigger bundle), it carries a real dependency tree (click, tabulate — note: do not pair it with
candidate #6 in one slate), and its optional native pieces (SpatiaLite, a gcc-built test extension,
ubuntu-only) must be explicitly excluded for the offline <10 min cross-platform bar. If jello's staleness
bothers the owner, sqlite-utils is the direct replacement for the CLI slot.

---

## 5. §2.3 criteria NOT satisfiable by read-only research — the clone-time checklist

These are exactly the checks the protocol assigns to the free feasibility phase (§5.1) and must land in
`CORPUS-MANIFEST.json` before the repos are proposed (§2.3 preamble), i.e. before the ≤ 08/12 B2-SPEND
decision (§5.2):

1. **C1 exact LOC** at the pinned SHA (`git ls-files` + line count) — only estimates above.
2. **C2 measured**: clean checkout → suite green on Linux **and** macOS, offline, with pinned toolchain,
   one full run < 10 min, times recorded. Special attention: mistune and bottle have ubuntu-only CI;
   csvkit's dependency tree may break the offline install.
3. **C3 verified**: write one real acceptance criterion per repo with the shipped probe catalog and run it.
4. **C6 archive sha256**: produce the tar of each pinned snapshot and record its digest.
5. Re-run the §1.1 independence grep at proposal time (the tree moves).

None of these requires a spend entry; all of them require the clone this research deliberately did not do.

---

## 6. What still needs the owner (out of scope here)

- **The B2-SPEND decision itself** (protocol §5.1, §5.2, plan §7 pack #1 item 4): repo list approval +
  evaluator slate + compensation/cap, in one decision, **≤ 2026-12-08**. This file is input to that package;
  it decides nothing.
- **Evaluator slate, remuneration, confidentiality terms, cap** (Q2, Q7): entirely the owner's; not
  researched here.
- **The language-diversity SHOULD** (§2.3 last ¶: ≥ 2 primary languages): every qualifying candidate found
  under the probe-catalog constraint (Python-callable probes; Python-pytest acceptance harnesses the
  evaluators can run) is Python. Meeting the SHOULD means adding a non-Python CLI subject measured through
  CLI-invocation/process-effect probes only, with a second pinned toolchain — feasible but it trades
  against the 26/01 oracle date (same trade Q12 records for repo count). Owner call: accept the single-
  language slate with this declared limitation, or direct a round-2 search for one non-Python CLI.
- Whether the slate takes an alternate swap (§4) — e.g. bottle in for explicit web-surface coverage.

---

*Research input only. Confers no approval, authorizes no contact, commits no spend. Prepared read-only on
2026-11-26 against the live GitHub API; every number above is re-verifiable at the cited URLs.*
