# G6 return playbook — what happens when `REPORT.md` arrives

Operator procedure for the external-validation record of **AISEF 1.7.2**. It
changes no gate semantics: every check below is either a command that already
exists or a comparison the closure probes already make. The authority on what
G6 *means* is `docs/PROJECT-CLOSURE-GATE.md` (§5 G6, §0b); this file only says
what to do, in what order, and when to stop.

Identity of the run this playbook serves (from
`closure-evidence/external-validation/1.7.2.bundle.json`):

| field | value |
|---|---|
| product | `aisef==1.7.2` from public PyPI |
| release tag | `v1.7.2` |
| release_source_sha | `d092b25fb94ec463347e6a5a04d1cc43a7fc2df8` |
| wheel sha256 | `d97ca56db1499f7eaf97ee0e1a4c3eff54acf08a7c6c66bd892c6943c1db63f9` |
| sdist sha256 | `7fe16a4f1fd26a56e5cba9717592082f503336ca41c517de395192ce189ef7a6` |
| protocol version | v1.1.0 |
| instructions_digest | `376c6e600865060a963b8cd3e4c5a12c918ca7a7b2e0d5125b0f88725698a973` |
| record path | `closure-evidence/external-validation/1.7.2/REPORT.md` |

Standing rules while the run is open: the bundle directory and the handoff
record are frozen; nobody on the implementation side writes `REPORT.md`; an AI
is not a participant; the participant is not coached toward any result.

## A. Preserve the original, byte for byte

1. Take the file exactly as returned. Record its digest before anything else:

   ```sh
   shasum -a 256 <returned REPORT.md>
   ```

2. Place it, unmodified, at `closure-evidence/external-validation/1.7.2/REPORT.md`.
   It is the **only** file added to that directory. Transcripts, screenshots or
   archives the participant returns go to
   `closure-evidence/external-validation/1.7.2-attachments/`, never inside the
   hashed directory.
3. Commit it alone, with the digest from step 1 in the commit message. This
   commit is `EVIDENCE_ONLY` under `docs/closure-gate.json#planes`; it moves
   HEAD and does not touch G1.0 (see L).
4. If the record needs normalising (encoding, line endings, a table the
   probes cannot read), write the normalised form as a **derived** file
   (`closure-evidence/external-validation/1.7.2-derived/REPORT.normalised.md`)
   with the original's digest in its header. The original is never edited; a
   correction from the participant is a dated addendum they write.

## B. Bind the record to the release node

Read what the record declares and compare it with the handoff record and the
release manifest. The reader is the probe's own:

```sh
python3 - <<'EOF'
import json, sys; sys.path.insert(0, ".")
from aisef.control.closure import declared_identity
rec = json.load(open("closure-evidence/external-validation/1.7.2.bundle.json"))
got = declared_identity(open("closure-evidence/external-validation/1.7.2/REPORT.md", encoding="utf-8").read())
for k in ("product_version", "release_tag", "release_source_sha", "wheel_sha256", "sdist_sha256", "protocol_version", "instructions_digest"):
    print(f"{k:22s} declared={got.get(k, '—')[:20]:22s} expected={str(rec[k])[:20]:22s} {'OK' if got.get(k, '') == str(rec[k]) else 'MISMATCH'}")
EOF
```

Every row must read `OK`. A mismatch is not repaired on our side: it is either
a transcription error the participant corrects by addendum, or evidence that a
different release or different instructions were validated (→ H, INVALID RUN).
The instructions digest is recomputed by the probe from the directory, so if
the directory holds anything but the six frozen files plus `REPORT.md`, remove
what does not belong (attachments go to `1.7.2-attachments/`) — never edit the
frozen files.

## C. Participant-required fields

Present and non-placeholder (`<...>` left in place means *not measured*, which
is a legitimate value only where the template says so):

- §1: the seven identity rows, report date, participant profile, the four
  yes/no rows (external person, read source, contributor, human), observer,
  OS/Python, client, Docker, target project;
- a `Participant:` line or row that asserts external, human status — this is
  what `probe_participant_external` reads (G6.2); an AI or a contributor cannot
  satisfy it, and the owner confirms the assertion at approval;
- §11 attestation signed by the participant, not on their behalf.

Nothing beyond what the template asks is collected.

## D. Protocol metrics

Every row of the protocol's Metrics table (`docs/EXTERNAL-VALIDATION-v1.1.0.md`
§ Metrics, frozen copy `PROTOCOL.md` in the bundle) must appear with its label
unchanged. `probe_external_report` fails on a missing label; do not rename a
row to make it match — ask the participant for an addendum.

## E. Classify findings

Findings stay in the participant's words. Severity is the protocol's own
ladder (P0 cannot install / data loss / security / incorrect gate result; P1
cannot complete without author help; P2 friction; P3 cosmetic). For each
finding, add a **derived** classification record (not in the report) under
`closure-evidence/external-validation/1.7.2-derived/findings.json`:

| field | meaning |
|---|---|
| `id` | F-1, F-2, … |
| `severity` | as the participant wrote it |
| `class` | `PRODUCT` (a `PRODUCT_AFFECTING` path must change to fix it) · `ASSURANCE` (tests, evidence tooling, closure/validation procedure) · `DOCUMENTATION` (a public document) · `ENVIRONMENT` (participant machine, network, agent CLI, model) · `NOT_A_DEFECT` |
| `plane_paths` | the paths a fix would touch, classified with `docs/closure-gate.json#planes` |
| `register` | the D-nnn id if it enters `docs/DEFECT-REGISTER.json`, else empty |

Class decides consequences (I, J); severity decides G6.3. A finding whose class
is ambiguous is recorded as `UNRESOLVED` and taken to the owner, never rounded
down to harmless.

**Known potential finding, recorded in advance:** the frozen `QUICKSTART.md`
in the bundle, copied verbatim from the tag, says *"Expect: Successfully
installed aisef-1.7.1"* and *"aisef --version → aisef 1.7.1"* in steps 1–2,
while `INSTRUCTIONS.md` pins `aisef==1.7.2`. The participant will see 1.7.2 and
may log the discrepancy. It is not pre-classified here and the participant is
not told about it; whatever they observe and however they grade it is the
record. The bundle is not edited for it.

## F. Run G6.1 → G6.2 → G6.3

```sh
python3 bin/aisef closure
```

Read the three G6 rows. Their meaning is fixed by the contract:

| criterion | PASSED when | otherwise |
|---|---|---|
| G6.1 | record present in the bundle, every protocol metric present, all seven identity fields equal the manifest and the bundle digest, onboarding digest unchanged | FAILED on a mismatch or a moved onboarding surface; UNRUNNABLE on a missing record, field or bundle |
| G6.2 | the record asserts an external human | FAILED for an AI or a non-external participant; UNRUNNABLE without a `Participant:` line |
| G6.3 | no unresolved P0/P1 in the findings table | FAILED with an unresolved P0/P1; UNRUNNABLE without a severity column |

G6.3 is the only waiver-eligible G6 criterion, and the owner has authorised no
waiver. A criterion is never edited to fit the record.

## G. Full closure projection

The same command prints all 27 criteria. Expected after a clean G6 **on a
release with no open P1**: 27 passed, `CLOSABLE`, approval `pending`. Since the
LedgerLock dogfood intake (2026-09-15) 1.7.2 carries three OPEN P1 defects
(D-026, D-028, D-029) and G2.3 reads FAILED, so a clean G6 on 1.7.2 projects to
26 of 27 at best; closing needs the owner's decision on a patch release (I, J). Re-check that G1.0 still reads PASSED with the
record committed — it will, unless a product path changed (L).

## H. Name the outcome

Exactly one of:

| outcome | condition | next |
|---|---|---|
| **PASS** | G6.1–G6.3 PASSED, no finding of class `PRODUCT` at P0/P1, no new P0/P1 anywhere | K |
| **PRODUCT DEFECT** | any finding of class `PRODUCT` at P0/P1, or an `UNRESOLVED` class the owner rules product | I, then J |
| **ASSURANCE/PROTOCOL DEFECT** | the run was valid but a test, recorder, probe reading, template or procedure was wrong (e.g. the probe cannot read a well-formed record) | register it; fix lives in the assurance plane; G6 outcome stands or is re-read — owner decides |
| **INVALID RUN** | the record does not bind to this release (B), the product was not installed from public PyPI, the participant is not an external human, the bundle was altered, or required evidence is missing and cannot be supplied by addendum | J: a new execution is required; nothing is inferred from the invalid one |
| **INCONCLUSIVE RUN** | the run bound and was valid but stopped for a reason outside the product (participant environment, agent CLI or model outage, unrelated infrastructure) before the lifecycle could complete | record why; owner decides whether a new execution is required |

An INVALID or INCONCLUSIVE run is never re-read as PASS.

## I. When a new patch release is required

Only when a fix must change a `PRODUCT_AFFECTING` path (`aisef/`,
`pyproject.toml`, license files): the product identity moves, G1.0 reads FAILED
by design, and the next release (1.7.3) is the candidate. A DOCUMENTATION,
ASSURANCE or EVIDENCE change never requires a release. Ambiguous → `UNRESOLVED`
→ owner.

## J. When another G6 execution is required

- after any new patch release (a new release node needs its own record and its
  own bundle, generated with `validation/make_validation_bundle.py <version>`);
- after an INVALID RUN;
- after an INCONCLUSIVE RUN, if the owner rules so;
- if the bundle or the onboarding surface had to change (G6.1 then reads
  FAILED and cannot be relabelled — see `tests/test_release_identity.py`).

A PASS with only DOCUMENTATION or ASSURANCE findings does **not** require
another execution.

## K. When the owner's approval is required

Always, and only the owner:

- confirming G6.2's assertion that the participant is a genuine external
  human (the probe reads the claim; a person verifies it);
- any waiver (none authorised);
- any `UNRESOLVED` classification;
- the decision after PRODUCT DEFECT, INVALID or INCONCLUSIVE outcomes;
- final closure itself:

  ```sh
  python3 bin/aisef closure --approve --note "<owner's note>"
  ```

  refused by the tool unless all 27 criteria are non-blocking and the contract
  is pinned. After it, commit `closure-evidence/closure-state.json`; that
  commit is `closure_record_sha`, and `docs/BASELINE-v1-CLOSED.md` is written
  only after this approval.

## L. Recording G6 evidence after release does not require 1.7.3

Under owner adjustment 8 a release is identified by its product digest and its
PyPI artifact digests, not by HEAD. Committing `REPORT.md`, the derived
records, the closure report or the owner's signature changes no
`PRODUCT_AFFECTING` path, so G1.0 stays PASSED and commit-bound evidence
(G1.2, G2.1, G2.2, G5.4) stays fresh. This is pinned by
`tests/test_release_identity.py::TestV1GRegressionMatrix::test_11_release_validate_record_close_converges_without_another_release`
and was observed on this repository: after `v1.7.2` (`d092b25`) the pin
commit, the evidence commit, the handoff commit and the documentation commit
each moved HEAD and G1.0 read PASSED every time.
