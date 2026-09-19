# W1 run 1 — first attempt, aborted by the kernel's own preflight (2026-09-17 14:00, $0, no model call)

Driver phases prepare (15/15 preflight checks), kernel-first (exit 2 on the stale readiness, no agent call) and approve
(ARB-1, only readiness changed) passed. `aisef run --client opencode` then stopped after 5 s at `sprint ERROR`:
"verification tools missing where they will run — `tools.sast` = `bandit -q -r .` — MISSING in
aisef-verify-python:b2c7afff2aed: exit 127 — fix the environment (`aisef doctor`) before paying for a session (D-028)".

Classification: a correctly typed ENVIRONMENT stop by the hardened kernel (SS-46 / INV-N.1: a DECLARED image is probed
for every tool the project will run, auto-detected ones included). The reference project pins that image; it never
contained bandit; the 1.7.3–1.7.6 runs on this project went ahead and produced `bandit` TOOL_UNRUNNABLE records instead
(run-2's F-B). An explicit empty `tools.sast` does not disable auto-detection (empty = auto), so the environment
contract had to be made consistent before a W1 run could start — the preparation record in P20 says what was changed
and why, and the finding is registered in the defect set. Nothing here is W1 qualification evidence; it is the record
of the stop and of the driver's phases up to it.
