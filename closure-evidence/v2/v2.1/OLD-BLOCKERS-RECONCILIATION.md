# V2.1 — re-reconciliation of the old blockers (owner decision 2026-10-28, step 4)

The fresh resume campaign (mw0/mw1) measured a 199-target slice at fce3d7b7 with **0 TIMEOUT / 0
INFRA / 0 NOT_RUN**. A clean campaign does **not** close a historical, unexplained failure: it did
not measure these targets, and it cannot exercise a rare product race. Each blocker is stated on its
own, with current evidence.

## `aisef2/app/bundle_cli.py::_create` — OPEN (not measured at head; kill-test soundness in doubt)

- **Status at fce3d7b7:** MISSING. Outside the mw0/mw1 slice (confirmed: not in either worker record).
  Its four historical results all fail reuse-proof; the most benign (measured on 4ec961e) is blocked by
  `KILLTESTS` (`tests/v2/test_v21_continue_usage.py` changed), with `MODULE` also in the union. So it has
  **no sound measurement at the candidate head** and the fresh campaign did not add one.
- **Kill set:** `test_v21_bundle_tools.py, test_v21_identity.py, test_v21_review.py,
  test_v21_continue_usage.py, test_v21_continue_integrity.py` — it **includes
  `test_v21_continue_integrity.py`**, the file whose baseline (T0) soundness is the open
  `continue_integrity` finding below. Historically _create was the single T0 FAIL observed for that file
  on a clean tree (PASS 27 / FAIL 1). That observation was **never** concluded to be load, flake, or bug
  (an earlier hasty "flaky" conclusion was retracted).
- **Net:** double-blocked. Even once _create is measured at head (step 5), the result is only sound if
  `test_v21_continue_integrity.py` passes T0 reliably — which the `continue_integrity` finding leaves
  unresolved. **Not waived; not closed by the fresh campaign.**

## `aisef2/app/cli.py::_parser` — OPEN (not measured at head; not waived)

- **Status at fce3d7b7:** MISSING. Outside the mw0/mw1 slice. Most benign result (4ec961e) blocked by
  `KILLTESTS` (`test_v21_continue_usage.py`); union also has `KILLSET` and `MODULE`.
- **Kill set** includes `test_v21_continue_integrity.py` as well, so the same T0-soundness dependency
  applies. The historical `_parser` symptom was "no-summary" (its kill run produced no summary — a hang
  or a cut result, never a clean KILLED/SURVIVED).
- **Per standing directive `_parser` is NOT waived.** It stays an explicit blocker until it is soundly
  measured at head. The fresh campaign did not measure it.

## Finding `continue_integrity` — OPEN (a suspected product race a clean run cannot exercise)

- **What it is:** `test_v21_continue_integrity.py` is the T0 kill-test of ~97 of the re-measure targets.
  On a clean tree its T0 showed an intermittent single FAIL (_create). The question left open: is a
  rare **product race** — S2 lost after an asynchronous SIGKILL in the "request sent, result/usage not
  yet journaled" window — being observed, or is it load / test / fixture?
- **What was ruled out (round-1 controlled fault injection, 2026-10-25, scratch worktree `inv-ci`):**
  in-process kills at the `provider/request` S2 journal boundary (before-write / short-write /
  after-write / after-fsync) are all **contract-correct** — S2 delivered, verdict PASS, cost marked
  "unknown: not 0", 0 violations. So the journal-request window is **not** the silent-drop source
  (those points kill before the client sends; the run re-develops S2 cleanly).
- **What is still open:** the original "before-step" window ("sent, not yet result") — an asynchronous
  SIGKILL from outside the process — was **not reproduced**; no product fix was written (no hypothesis
  patch before a reproduction). **Blocker remains OPEN.**
- **Why the fresh campaign does not close it:** mw0/mw1 ran clean (0 TIMEOUT/INFRA). A clean run does not
  inject the fault and so says nothing about a rare lost-S2 under async SIGKILL. 0 TIMEOUT/INFRA is
  evidence of a clean *measurement environment*, not of the *absence of the race*.

## Consequence for step 5

`_create` and `_parser` are in the 62 MISSING and must be measured at the merged head. But their kill
sets include `test_v21_continue_integrity.py`, whose T0 soundness is the open `continue_integrity`
finding. The step-5 scope must therefore flag any target whose kill set includes
`test_v21_continue_integrity.py` as **"measure, but result soundness gated on the continue_integrity
finding"** — measuring them does not by itself retire that finding. No new investigation is opened in
this round (owner constraint); the finding is carried, stated, and surfaced for the owner.
