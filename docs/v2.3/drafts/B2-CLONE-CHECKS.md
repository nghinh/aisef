> **SUPERSEDED BY SCOPE AMENDMENT — retained as historical prep only.** [SCOPE AMENDMENT 2026-11-26: REMOVED_FROM_V2.3_RELEASE_SCOPE_BY_OWNER — see amendments/SCOPE-B2-EXTERNAL-REMOVED.md]

# B2 clone feasibility checks — three owner-candidate public repos

**measured input to the B2-SPEND package — confers no approval**

Measured 2026-11-26 (+07) on macOS (Darwin 25.5.0, Apple Silicon), Python 3.14.7
(`/opt/homebrew/bin/python3`), per `docs/v2.3/drafts/B2-GROUND-TRUTH-PROTOCOL-DRAFT.md` §2.3.
Owner directive 2026-11-26 P3. All work in an isolated scratch root (one clone + one venv per
repo; interpreters never run with cwd inside a clone except each repo's own suite via its venv).
Network used only for `git clone` and `pip install`; suites ran with proxy env pointed at a dead
port. Raw logs: `/Users/nghinh/Downloads/projects/aisef-private-evidence/2026-11-26-b2-clone-checks/`.

## Results

| Criterion | jello v1.6.1 | mistune v3.4.0 | tinydb v4.9.0 |
|---|---|---|---|
| Pinned SHA (tag verified →) | `b43c9b24605ce2fca7bb303cdd845f8e814c15fa` | `f19057fdf339affb61ca63c7fe28df7a951ec588` | `1e39ad3a2d9eca57efd9019fd089b5a04676da95` |
| C6 `git archive --format=tar` sha256 | `9cf7e27653ece7da967bec51a1d6a8b496fcf03e4dbadaf102990a229f857f30` | `66f0376cf6d64acc91d606146a97b0dde5c87eabef968871184592a17d498100` | `15bfbda9ce7b83c66a2d9ba8656f890b9b34241bbbfb9ab86a95887cb4451123` |
| C4 license (SPDX) | MIT | BSD-3-Clause | MIT |
| C4 LICENSE sha256 | `1a404c97debd32c80005736bd368078ccc8f858c8ebafa2576b0c3919afb92c4` | `539013fd8e19f744f8bf0e27a532bbff54cd689ecef7a800f56ae5dc824be870` | `b0e2a2d39271e3d96b717d7be8235ac413d74797bf7f742f0801cfaad6c8c912` |
| C1 LOC (`git ls-files '*.py'` + `wc -l`) | 7,023 in 12 files — **inside** 1,000–200,000 | 9,237 in 67 files — **inside** 1,000–200,000 | 4,665 in 21 files — **inside** 1,000–200,000 |
| C2 suite result | `python -m unittest discover tests`: 203 tests OK, 1 skipped | `python -m pytest`: 1,324 passed | `python -m pytest`: 218 passed, 1 skipped |
| C2 wall time vs <10 min bar | 0.35 s real — **PASS** | 3.53 s real — **PASS** | 1.25 s real — **PASS** |
| C2 network during tests | none observed (dead-proxy env, no failures) | none observed | none observed |
| C2 install route | `pip install -e .` (pulls Pygments) | `pip install -e . pytest` | `pip install -e . pytest` **+ pytest-cov** (required, see notes) |
| C3 acceptance probe | VERIFIED (CLI, exact stdout + exit 0) | VERIFIED (Python callable, exact HTML) | VERIFIED (callable + file artifact shape) |

Verdict: all three repos PASS every criterion measured here (C1, C2 macOS leg, C3, C4, C6).
No criterion FAILED.

## C3 probe transcripts

Probe scripts live outside the clones (`b2checks/probes/`, copied to the evidence dir).

**jello** — venv CLI, JSON on stdin:

```
printf '{"foo": [1, 2, 3]}' | <venv>/bin/jello '_["foo"][1]'
PROBE jello: VERIFIED (stdout='2', exit=0)
```

**mistune** — venv python, known CommonMark example:

```
<venv>/bin/python -I probe_mistune.py   # mistune.html("# Hello *world*")
PROBE mistune: VERIFIED (html='<h1>Hello <em>world</em></h1>\n')
```

**tinydb** — venv python, insert + query + JSON storage file shape:

```
<venv>/bin/python -I probe_tinydb.py
PROBE tinydb: VERIFIED (query hit={'name': 'probe', 'n': 1}, file shape={'_default': {'1': {'name': 'probe', 'n': 1}}})
```

## Surprises / notes

- **tinydb:** plain `pip install -e . pytest` is NOT sufficient — `pytest.ini` hardcodes
  `--cov`/`--cov-append`/`--cov-report` in `addopts`, so the first run exited 4 (unrecognized
  arguments) until `pytest-cov` was installed. One test (`test_storages.py::test_yaml`) skips
  without PyYAML. No warnings otherwise.
- **jello:** 1 skipped test — an HTML-output test gated on exactly `Pygments 2.9.0`
  (installed: 2.21.0). Benign version-pin skip; suite otherwise OK.
- **mistune:** ships `uv.lock` (uv-pinned dev deps). The plain-pip route used here (unpinned
  pytest 9.2.0) passed 1,324/1,324, so the unlocked route suffices; a locked rerun would pin a
  different pytest. No warnings.
- All three are pure Python (no native deps), no deprecation warnings in any suite log, no
  flakiness observed (single run each).
- Offline guard is soft: `http(s)_proxy` pointed at a dead port catches HTTP-library traffic
  only; no raw-socket use was observed in any suite.

## Versions used (per-venv pip freeze, full list in `versions.log`)

- jello venv: jello 1.6.1, Pygments 2.21.0
- mistune venv: mistune 3.4.0, pytest 9.2.0
- tinydb venv: tinydb 4.9.0, pytest 9.2.0, pytest-cov 7.1.0, coverage 7.17.5

## Remaining gaps (not measured here)

- **Linux leg of §2.3(2)** — green suite with pinned toolchain on Linux is CI's side; still owed
  before selection.
- **§2.3(5) independence re-grep at proposal time** — the repos-nowhere-in-AISEF-history check
  must be re-run against the repo state current at the moment the proposal goes to the owner.
- Pinned-toolchain statement (exact interpreter/dep pins per repo) to be frozen in
  `CORPUS-MANIFEST.json` at proposal time; this document records what was measured, not pins.
- Selection into the corpus remains owner-approved under B2-SPEND (§5); this is a feasibility
  measurement only.
