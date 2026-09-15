# TEMPLATE — external validation report (G6)

> `status: TEMPLATE_NOT_EVIDENCE`
>
> **This file is a blank form. It is not a validation record, and it must never
> be cited as one.** Nothing in it has been observed. Every value is a
> placeholder written as `<...>`; a placeholder left in place means the field was
> not measured, not that it was zero or fine.
>
> The record this form produces belongs at
> **`closure-evidence/external-validation/<version>/REPORT.md`** — inside the
> immutable bundle for the release being validated, the path
> [`docs/EXTERNAL-VALIDATION-v1.1.0.md`](EXTERNAL-VALIDATION-v1.1.0.md) declares
> and gate **G6.1** reads. That file does not exist yet and must not be created
> by anyone other than a real participant (or an observer transcribing one).
> **An AI agent cannot satisfy G6, and neither can an AISEF contributor**
> ([`PROJECT-CLOSURE-GATE.md`](PROJECT-CLOSURE-GATE.md) §0 ruling 4). Filling
> this form in from imagination is the one failure that cannot be repaired later,
> because a fabricated record is indistinguishable from a real one afterwards.

**How to use it.** Copy to the path above, delete this banner (including the
`status:` line), fill in every `<...>`, and leave nothing blank — "not measured"
is a legitimate answer and a better one than a guess. The participant's
walkthrough is
[`EXTERNAL-VALIDATION-QUICKSTART.md`](EXTERNAL-VALIDATION-QUICKSTART.md); the
protocol and the observer rules are in
[`EXTERNAL-VALIDATION-v1.1.0.md`](EXTERNAL-VALIDATION-v1.1.0.md).

---

## 1. Run identity

The first seven rows bind this record to **one public release** and to the
**exact instructions** followed. Gate G6.1 compares each of them with the
release manifest and the bundle on disk: a record for another release, or one
run against edited instructions, is not evidence for this closure. Copy the
values from `1.7.3.bundle.json` next to this folder; do not type them from memory.

| field | value |
|---|---|
| Product version | `1.7.3` |
| Release tag | `v1.7.3` |
| Release source SHA | `cfee273074af2000e0839c71333cf84ee8b5b73b` |
| Wheel sha256 | `97cd7a0fcaf3940b83fd5e83760da616632c4836208079398273c89b5fea6dcf` |
| Sdist sha256 | `7eafcc12aa6ddaa5ce07a93cab28795a0a3b7c49ac9a3fd3509eb290a032344d` |
| Protocol version | `v1.1.0` |
| Instructions digest | `<instructions_digest from 1.7.3.bundle.json, next to this folder>` |
| Report date | `<YYYY-MM-DD>` |
| AISEF version validated | `<aisef --version output>` |
| Onboarding digest at validation time | `<digest from closure-evidence/onboarding-digest.json>` |
| Participant profile | `<U1 software engineer | U2 engineering lead | U3 non-contributor>` |
| Participant is a genuinely external **person** | `<yes | no>` — G6.2 |
| Participant has read AISEF source | `<yes | no>` |
| Participant is an AISEF contributor | `<yes | no>` — must be **no** |
| Participant is a human being, not an agent | `<yes | no>` — must be **yes** |
| Observer | `<name or role>` |
| OS / Python | `<e.g. macOS 15.5 / Python 3.12.4>` |
| Client used | `<claude | opencode>` |
| Docker available during the run | `<yes | no>` |
| Target project | `<path or description>` |

G6.2 is not machine-decidable. The four rows above are the record's own
assertion; the owner confirms them at approval.

## 2. Metrics

Every row of the protocol's Metrics table, in its order. Do not rename a row —
the gate reads these labels.

| Metric | Type | Value |
|---|---|---|
| Install success | bool | `<yes | no>` |
| Time to first success (any gate passes) | minutes | `<n>` |
| Clarification requests | count | `<n>` |
| Undocumented steps discovered | count | `<n>` (list them in §3) |
| Command failures | count + details | `<n>` (details in §4) |
| Framework bugs | count + details | `<n>` (details in §5) |
| Agent bugs | count + details | `<n>` (details in §5) |
| Config mistakes | count + details | `<n>` |
| Full lifecycle completed | bool | `<yes | no>` |
| Total elapsed time | minutes | `<n>` |
| Estimated cost (API usage) | USD | `<n.nn>` |
| User confidence (1–5) | scale | `<n>` |
| Usability rating (1–5) | scale | `<n>` |
| Would use again | yes/no + reason | `<yes | no>` — `<reason>` |

## 3. Undocumented steps

Anything the participant had to do that no public document told them to do —
including things they worked out themselves. One row each; an empty table means
"none found", so say so explicitly.

| # | where in the walkthrough | what had to be done | how they found out | severity |
|---|---|---|---|---|
| 1 | `<step>` | `<action>` | `<guessed / read source / asked / error message>` | `<P0–P3>` |

## 4. Command log

The real sequence, including the wrong turns. Wrong turns are the data.

| # | command as typed | exit | outcome |
|---|---|---|---|
| 1 | `<command>` | `<rc>` | `<what happened>` |

## 5. Framework defects found

Framework problem vs agent problem — the protocol's Q7. Severities use the
protocol's **existing** P0–P3 ladder
([`EXTERNAL-VALIDATION-v1.1.0.md` § Finding classification](EXTERNAL-VALIDATION-v1.1.0.md#finding-classification));
do not invent a second scale. Leave `taxonomy` blank — numbers are assigned
centrally in [`FAILURE-TAXONOMY.md`](FAILURE-TAXONOMY.md) and
[`DEFECT-REGISTER.json`](DEFECT-REGISTER.json).

| # | severity | framework or agent | what happened | reproduction | status | taxonomy |
|---|---|---|---|---|---|---|
| 1 | `<P0–P3>` | `<framework | agent>` | `<observed>` | `<commands>` | `<open / fixed in vX.Y.Z / waived>` | |

## 6. User blockers and author interventions

An **author intervention** is any moment an AISEF author or contributor said or
typed anything that moved the run forward. The protocol's observer rule: blocked
more than 10 minutes on one step → minimal unblocking help, recorded as **P1**.

| # | minute | step | what the participant was blocked by | intervention given (verbatim) | severity |
|---|---|---|---|---|---|
| 1 | `<n>` | `<step>` | `<blocker>` | `<none / what was said>` | `<P0–P3>` |

Total author interventions: `<n>`. A successful canonical run requires **0**
(protocol exit criteria).

## 7. Confusion points

The protocol's Q5 — where they paused, reread, or ran the wrong thing.

| # | moment | what was unclear | what would have prevented it |
|---|---|---|---|
| 1 | `<step>` | `<...>` | `<...>` |

## 8. Lifecycle phases reached

| phase | command | reached | notes |
|---|---|---|---|
| install | `pip install aisef` | `<yes | no>` | |
| diagnose | `aisef doctor` | `<yes | no>` | |
| initialise | `aisef init` | `<yes | no>` | |
| set up skills and rules | `aisef setup` | `<yes | no>` | |
| wire guards | `aisef compile` | `<yes | no>` | |
| plan | `aisef plan` | `<yes | no>` | first step that spends money |
| human gates | `aisef gates` / `aisef approve …` | `<yes | no>` | |
| implement | `aisef run` | `<yes | no>` | |
| verify | `aisef qa` | `<yes | no>` | |
| pre-deploy | `aisef pre-deploy` | `<yes | no>` | |

## 9. Feedback questionnaire

The protocol's ten questions, answered in the participant's own words. Do not
paraphrase them into agreement.

1. In your own words, what does AISEF do? — `<...>`
2. Installation difficulty (1 trivial – 5 impossible): `<n>` — `<...>`
3. Documentation clarity (1 crystal clear – 5 incomprehensible): `<n>` — `<...>`
4. Single most confusing moment: `<...>`
5. Did any command fail unexpectedly? Which? — `<...>`
6. Did you understand why each step existed? — `<...>`
7. Overall experience (1 excellent – 5 terrible): `<n>` — `<...>`
8. Would you use AISEF on a real project? Why or why not? — `<...>`
9. The one thing you would change: `<...>`
10. Anything else: `<...>`

## 10. Exit criteria status

Copied from the protocol so the record answers its own gate. G6.3 fails on any
unresolved P0/P1 unless the owner waives it with a reason.

- [ ] >= 1 genuinely external user completed the full lifecycle
- [ ] No author intervention required for the successful canonical run
- [ ] All P0 findings resolved
- [ ] Material P1 onboarding blockers resolved
- [ ] Public docs match the actual workflow

Unresolved P0: `<n>` · unresolved P1: `<n>` · waived (with owner reason): `<n>`

## 11. Attestation

Signed by the participant, not on their behalf.

| | |
|---|---|
| Participant | `<name or pseudonym>` |
| Relationship to AISEF | `<none / user of X / …>` — "none" is the expected answer |
| I am a human being and I ran these commands myself | `<signature / date>` |
| Observer countersignature | `<name / date>` |
