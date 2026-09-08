# Engineering principles

The first four principles restate Andrej Karpathy's observations on
working with coding agents (source: `multica-ai/andrej-karpathy-skills`).
Rewritten in this framework's language because the original repo has no
license — reference is fine, repackaging is not.

## 1. Understand before you write

Read the requirement, trace the real flow, identify the right place to
change — then type the first line. Most defects come not from writing bad
code, but from writing a correct solution to the wrong problem.

When a requirement is ambiguous: surface the ambiguity, do not pick
silently. When a simpler approach exists: say so. If there is no human in
the loop, record the assumption in the artifact and continue — do not
block waiting.

## 2. Simple first

Write exactly enough code to solve today's problem. No abstraction layer
for a single call site, no parameterization for a value that has never
changed, no scaffolding for work nobody has requested.

Standard library before external libraries. Built-in platform features
before hand-written code. One line beats five — but only when the one
line is still correct at the edge cases.

## 3. Change only what needs changing

Touch exactly what the task demands. Do not "while you're here" reformat,
rename, or clean up neighboring code in the same change — that inflates
the diff and hides what actually changed.

When fixing a bug, find the root cause, do not patch the symptom in one
call site. One fix where all callers route through is a smaller diff than
separate patches in each caller, and it does not miss any.

## 4. Serve the goal, not the wording

Know what this task serves. When the wording of a task conflicts with its
goal, surface the conflict instead of following the letter and delivering
something useless.

## 5. Evidence, not self-report

Do not declare "done", "fixed", or "tests green" without a fresh, actual
run result. Define measurable success criteria **before** starting. Write
a test that reproduces the bug before fixing it.

This principle is the foundation of every quality gate in the framework:
gates read only the output of external processes, never the agent's
self-assessment.

## 6. Stop on contradiction

Documents disagree, mockup contradicts architecture, requirements are
self-negating — stop and report. Do not silently pick one side and
continue.

Precedence when arbitration is needed: architecture > UX spec > visual
contract from mockup.

## 7. Declare what is missing

If a mechanism is absent (sandbox will not run, hook cannot attach,
reviewer is not independent), record the reduced assurance level
explicitly in the artifact. Silently pretending everything is in place is
the worst kind of failure, because it removes even the ability to know
something is missing.
