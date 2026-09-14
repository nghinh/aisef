# External Validation Protocol — v1.1.0

> **Objective**: Prove that AISEF can be successfully used by someone
> other than its author.

## Why this matters

AISEF v1.0.0 was built, tested, and dogfooded exclusively by its author.
Every successful run relied on undocumented knowledge: which config keys
matter, which model providers work, which commands to run in which order,
and what to do when something fails. A framework that only its author can
operate is a personal tool, not a product.

v1.1.0 ships when an external user completes the full lifecycle without
author intervention.

## Target users

| # | Profile | Why |
|---|---------|-----|
| U1 | Software engineer, no prior AISEF exposure | Tests cold-start onboarding |
| U2 | Engineering lead / platform engineer | Tests whether AISEF fits real team workflows |
| U3 | Non-contributor (has not read AISEF source) | Tests documentation completeness |

At least one genuinely external user (U3) must complete the lifecycle.
Preferably 3+ runs total across profiles.

## Validation questions

Each run must answer:

| # | Question | Measured by |
|---|----------|-------------|
| Q1 | Can a new user understand what AISEF is? | Time to articulate AISEF's purpose after reading README |
| Q2 | Can they install it without assistance? | `pip install aisef` success, `aisef doctor` green |
| Q3 | Can they initialize a real project? | `aisef init` produces valid config, user creates requirements.md |
| Q4 | Can they complete plan → implement → verify → pre-deploy? | Each phase runs to completion without author help |
| Q5 | Where do they become confused? | Clarification requests, pauses, wrong commands |
| Q6 | What manual intervention is required? | Count and nature of author assists |
| Q7 | Framework problem vs agent problem? | Classification of each failure |
| Q8 | Would they use it again? | Post-run questionnaire (1–5 scale + open text) |

## Protocol

### Prerequisites (provided to tester)

- Python >= 3.11
- An AI coding agent (Claude Code or OpenCode) with API access
- A GitHub/GitLab account (for the test project)
- ~30-60 minutes
- No prior AISEF knowledge required

### Materials (Phase 3 deliverables)

1. **Quick Start** — 5-minute path from install to first successful gate →
   [EXTERNAL-VALIDATION-QUICKSTART.md](EXTERNAL-VALIDATION-QUICKSTART.md)
2. **User Guide** — full lifecycle reference → [USAGE-GUIDE.md](USAGE-GUIDE.md)
   (English), [HUONG-DAN-SU-DUNG.md](HUONG-DAN-SU-DUNG.md) (Vietnamese)
3. **Sample project** — requirements.md pre-written, in the quickstart's step 6.
   *(An `examples/calculator/` directory was planned and never created; the
   four-line sample in the quickstart replaces it.)*
4. **Troubleshooting guide** — common errors and fixes →
   [USAGE-GUIDE.md](USAGE-GUIDE.md) §16, plus "When something fails" in the
   quickstart
5. **Expected outputs** — what success looks like at each step → the quickstart
   records the real output of every free step
6. **Issue template** — structured failure report → §5 and §6 of
   [TEMPLATE-EXTERNAL-VALIDATION-REPORT.md](TEMPLATE-EXTERNAL-VALIDATION-REPORT.md)
7. **Feedback questionnaire** — post-run survey → this document's last section,
   transcribed into §9 of the report template

### Run procedure

1. Tester works on a clean machine or clean venv
2. Tester follows only public documentation (README → Quick Start → User Guide)
3. No author assistance unless tester is completely blocked (record every assist)
4. Tester works through the canonical sample project:
   - `pip install aisef`
   - `aisef doctor`
   - `aisef init`
   - Write or use provided `docs/requirements.md`
   - `aisef plan`
   - `aisef run` (agent executes stories)
   - `aisef verify`
   - `aisef pre-deploy`
5. Tester records observations in real-time (screen recording encouraged)
6. Tester completes feedback questionnaire

### Observer rules

- Do not answer questions preemptively
- Record the exact moment and nature of every assist
- If tester is blocked >10 minutes on a single step, offer minimal unblocking help and record it as P1
- Do not optimize or coach during the run

## Metrics

Collected per run:

| Metric | Type |
|--------|------|
| Install success | bool |
| Time to first success (any gate passes) | minutes |
| Clarification requests | count |
| Undocumented steps discovered | count |
| Command failures | count + details |
| Framework bugs | count + details |
| Agent bugs | count + details |
| Config mistakes | count + details |
| Full lifecycle completed | bool |
| Total elapsed time | minutes |
| Estimated cost (API usage) | USD |
| User confidence (1–5) | scale |
| Usability rating (1–5) | scale |
| Would use again | yes/no + reason |

## Finding classification

| Severity | Definition | Action |
|----------|-----------|--------|
| P0 | Cannot install, data loss, security issue, incorrect gate result | Must fix before v1.1.0 |
| P1 | Cannot complete lifecycle without author assistance | Must fix before v1.1.0 |
| P2 | Significant confusion, DX friction, unclear docs | Fix if time permits |
| P3 | Cosmetic or optional improvement | Backlog |

## Exit criteria for v1.1.0

All of:

- [ ] >= 1 genuinely external user completes the full lifecycle
- [ ] Preferably >= 3 validation runs total
- [ ] No author intervention required for the successful canonical run
- [ ] All P0 findings resolved
- [ ] Material P1 onboarding blockers resolved
- [ ] Clean `pip install aisef` verified on fresh venv
- [ ] Claude Code and OpenCode conformance green (10/10)
- [ ] OpenCode+Serena write-scope behavior resolved or documented
- [ ] Public docs match actual workflow
- [ ] External validation report published (`docs/EXTERNAL-VALIDATION-REPORT-v1.1.0.md`)

## Feedback questionnaire

Post-run, tester answers:

1. In your own words, what does AISEF do?
2. Rate installation difficulty (1=trivial, 5=impossible)
3. Rate documentation clarity (1=crystal clear, 5=incomprehensible)
4. What was the single most confusing moment?
5. Did any command fail unexpectedly? Which?
6. Did you understand why each step existed?
7. Rate overall experience (1=excellent, 5=terrible)
8. Would you use AISEF on a real project? Why or why not?
9. What one thing would you change?
10. Any other feedback?
