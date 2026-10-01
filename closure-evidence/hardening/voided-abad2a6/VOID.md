# VOID — W0 qualification and candidate freeze at abad2a6

Status: **VOID — NOT QUALIFICATION EVIDENCE.** Retained unedited as the record of what was measured on 2026-09-17,
never as a claim about any candidate.

- `AISEF-W0-QUALIFICATION.json` — W0 at `abad2a6`, written 06:59 with 10/10 criteria holding, voided at 15:14 the same
  day (the `voided` block inside the file states it): W1 run 1 found **SS-65** (P1) on that very candidate at 14:00,
  so the criterion "0 P0/P1 open" stopped holding for `abad2a6`. `qualified` in the file is already `false`.
- `P19-FREEZE.json` — the freeze of `abad2a6` (`aisef/` tree `84014c98…`, wheel `aisef 1.7.6`). It rests entirely on
  the W0 record above and is void with it. The file is unedited; this note is its void marker.

Why the whole record and not a patch: SS-65 was a capability-model defect, not a missing binary. Fixing it changed the
product tree (`84014c98…` → `02a34e0e…`), so nothing measured on the old tree — including the 100 000-trace Phase 12
dataset run on it, kept separately under `phase12/history-kernel-84014c98/` — can stand in for a measurement on the new
one. The replacements are written fresh at the canonical paths: `AISEF-W0-QUALIFICATION.json` and `P19-FREEZE.json`.

Owner decision "FIX SS-65 AT CAPABILITY-MODEL LEVEL AND RE-QUALIFY", items 11–12.
