# DRAFT — owner ledger entry seq 14 (PIN-57 Option C: registry 57 → 59, recorder retained, ground-truth scope). Not evidence until the owner commits it.

**Status: DRAFT — becomes authority only when the owner issues it through the ledger with these digests.**
Owner ruling 2026-11-26 §3 (quoted): "selected PIN-57 OPTION C (mixed): register+calibrate `f5_gate` and
`released_evidence` (registry 57→59); keep `f5_recorder` outside ONLY while observation data cannot serve as
qualification authority"; "account explicitly for the 4 new validation/v23/ground_truth modules in the Q0 scope
review (they are tooling today — propose NOT_CHECKERS_V23 entries with the promotion clause)"; "the three existing
Q0 54/57 failures must REMAIN visible (do not touch b1_bindings/currency_dag/mutation calibration states)".
That ruling authorized development and testing of this amendment; it did NOT authorize landing it — this draft and
its patch go back to the owner. Per PIN-57 ruling §4 (2026-11-25), no implied approval is granted or taken.

The agent never writes `closure-evidence/v2/cycle2/RELEASE-DECISIONS.json`. If the owner approves, the owner (or the
agent on the owner's explicit instruction naming this entry and this digest) appends exactly this object as entry 14,
replacing only the `authority` placeholder with the owner's own words, which must quote the digest below; entries
1–13 stay byte-identical (CT-5, CIGOV-R1 append-only). Applying `docs/v2.3/drafts/SEQ14-PIN57-C.patch` on the branch
and committing it is likewise the owner's act (or the agent's on that explicit instruction).

```json
{
 "seq": 14,
 "id": "AISEF_V2_3_PIN57_OPTION_C",
 "authority": "<owner's own words, quoted verbatim, with date and channel, naming the ruling digest stated below this block>",
 "approver": "human:owner",
 "decision": {
  "AMENDS": "ledger seq 13 AISEF_V2_3_QUALIFICATION_ROUND_AUTHORIZED (committed; canonical ruling digest a1469d009f2456fccde4a3b3e3706a993e6bc1524b5512873dbcefe6ccec01f0, docs/v2.3/drafts/LEDGER-SEQ-13-DRAFT-R6.md). Seq 13 is immutable; this entry supersedes the exactly-named clauses in SUPERSEDES below, for the exactly-named files, and nothing else.",
  "PIN_57_OPTION_C": "Owner ruling 2026-11-26 §3 (PIN-57, docs/v2.3/drafts/PIN-57-AMENDMENT-CANDIDATES.md §4; evidence docs/v2.3/evidence/PIN-57-MODULE-ROLES.md): the two verdict-determining v2.3 checkers are registered and calibrated — validation/v2/checker_calibration.py REGISTRY += [_f5_gate, _released_evidence] (57 -> 59; their committed known-bad fixtures tests/v2/fixtures/known_bad/f5_gate.json blob 912daa2d1d080d9bfc1c608d473cff261ab3369d and tests/v2/fixtures/known_bad/released_evidence.json blob f978ebfb72c3935a18ab4cfc580d29baedb8a0d6 are unchanged). From registration the Q0 round's own obligations cover them automatically: Q0RoundV23's fixture test and anti-gaming sweeps run over cc.REGISTRY, and the first --write of the round-v2.3 Q0 record (still refused while any rule fails) will carry 59 rows with delta() printing '+ f5_gate' and '+ released_evidence' for owner review. f5_recorder stays outside the registry (V23_CHECKERS = (_f5_recorder,)) ONLY while its observation data cannot serve as qualification authority — see NO_OBSERVATION_AUTHORITY.",
  "PINS": "The pinned counts in tests/v23/test_v23_q0_round.py move with the registry under this same ruling: the Q0History synthetic pin becomes calibrated_count=58 and 'calibrated 58 of 59 registered checkers'; Q0RoundV23's count pin keeps its text (self.assertEqual(self.result[\"calibrated_count\"], len(cc.REGISTRY)), value now 59); Q0Record.setUpClass extends the committed 57-row v2.2 record with one synthetic calibrated row per registered v2.3 checker (f5_gate, released_evidence) and checker_count=calibrated_count=59, because the fully-calibrated fixture those writer/checker round-trips assume no longer exists at 57 rows after registry growth (the third pin, PIN-57-AMENDMENT-CANDIDATES.md §2.2). No v2.2 checker's contract (package, fixture, expected, fixture bytes) changes.",
  "NOT_CHECKERS_V23": "validation/v23/q0_round.py NOT_CHECKERS_V23 grows by exactly five files, each ruled here: (1) validation/v23/observe.py — the F5 recorder, an owner-ruled non-checker ONLY while no gate consumes its observation data as qualification authority (PIN-57-MODULE-ROLES.md §3.3/§3.5), its calibration and that condition drift-pinned always-run by tests/v23/test_v23_unregistered_checkers.py; (2-5) validation/v23/ground_truth/{__init__,corpus,labels,metrics}.py — B2 Tier-0 ground-truth tooling (protocol §8 prep), tooling and not checkers: no gate consumes their output and no known-bad fixture exists, the absence pinned by the same test file. Promotion clause: when ground_truth/corpus.py --check becomes a gate at the B2 manifest (W6), it enters cc.REGISTRY with a calibrated checker and leaves the list — a new q0_round.py, a new patch, a new ruling. The list stays closed.",
  "NO_OBSERVATION_AUTHORITY": "Why f5_recorder's observation data cannot serve as qualification authority today, cited to code: no gate, guard, workflow or round-gated test passes observations to the engine — validation/v23/ci_gate.py:173, validation/v2/mutation.py:2855/2868 and tests/v23/test_v23_rounds.py (_f5_states) all call impact.classify without the parameter, and no .github workflow passes --observations (grep 2026-11-26); the only consumer is impact.py's own CLI (validation/v23/impact.py:1577-1582, 'an input only'); an observation-based reuse can never carry an acceptance basis — it carries observation:<sha256>@<base> with evidence.authority = impact.OBSERVATION_AUTHORITY, the 'none: ...' sentinel (impact.py:136, applied at :1198-1200), which ci_gate.reuse_problems requires intact (ci_gate.py:143-145) and tests/v23/test_v23_review1.py:308 (PROV-1) pins; the owner ruling of 2026-11-21 is quoted in the module docstrings (observe.py:6-9, impact.py:30-31). The retention CONDITION is pinned always-run by tests/v23/test_v23_unregistered_checkers.py::UnregisteredCheckers.test_the_observations_input_of_the_engine_stays_unwired: any wiring of observations into a gate re-opens PIN-57 Decision 2 for this module and requires registration/calibration or a new exact owner ruling.",
  "GATED_TEST_WIRING": "exactly docs/v2.3/drafts/SEQ14-PIN57-C.patch (sha256 ed7a55d89368707dc1897d191a6e1fdd70ad8f5b70ab74ffec9dc21e4236baac), cumulative over the committed tree (HEAD 50960ffa1f398a0ae112a38f70540d65d7bbfa33 = v2.2.0 + SEQ13-WIRING-R6.patch for tests/v2/sealing_gate.py), touching exactly: tests/v2/sealing_gate.py (V23_PINNED re-pins for the three edited pinned files, nothing else; GATED, V22_REPLAYED, V22_REPLAYED_Q0 and the sealing mechanism stay as seq 13 ruled), tests/v23/test_v23_q0_round.py (the PINS edits), tests/v23/test_v23_rounds.py (SEQ14 constants; wired_sealing_gate applies the patch stack; Seq13Wiring additionally requires sealing_gate.py == v2.2.0 + SEQ13-WIRING-R6.patch + this patch's sealing_gate hunks, and this patch's sha256 named by this draft), tests/v23/test_v23_seq13_wiring.py (WiringR6 verifies the stacked wiring; the seq-13 patch alone now skips nothing, like R2-R5 before it; the seq-14 patch's file set is closed and its sha is this draft's), tests/v23/test_v23_unregistered_checkers.py (new, always-run drift pins), validation/v2/checker_calibration.py (REGISTRY growth), validation/v23/q0_round.py (NOT_CHECKERS_V23 growth). FILE_DIGESTS binds every touched file before and after.",
  "FILE_DIGESTS": {
   "patch_sha256_lf": "ed7a55d89368707dc1897d191a6e1fdd70ad8f5b70ab74ffec9dc21e4236baac",
   "measured_at": "HEAD 50960ffa1f398a0ae112a38f70540d65d7bbfa33 (release/v2.3-big), 2026-11-26",
   "git_blob_sha1_before_to_after": {
    "tests/v2/sealing_gate.py": ["f6b64b5264fb55a6863145bc7722ec869d1f2535", "90adf82e49fce5204c472721cc0326ff0b3e5934"],
    "tests/v23/test_v23_q0_round.py": ["8d518bf8f392300a6d5e280d74f6a2f3e360a5d6", "2f01c39d2d4ab9af266eca77e159c0a295906f37"],
    "tests/v23/test_v23_rounds.py": ["a8eb0a0c7b3ae6c1644a854338ef3e4cae8099e4", "83aafa51cdc7984c6918b8c836671726af1079b8"],
    "tests/v23/test_v23_seq13_wiring.py": ["5891086854f9e98b8b01e639aadd79b497f9cb93", "fa51360733e20e115475fd77dc73cf9afe3fb69b"],
    "tests/v23/test_v23_unregistered_checkers.py": [null, "4b20886ae8b1ad3677e484f2e8a97ade575189b5"],
    "validation/v2/checker_calibration.py": ["56bf4453ad02aa907e39c4b8e0942c3387775915", "e9736ee7d41388030bf67db066c393e105adb7bd"],
    "validation/v23/q0_round.py": ["d74edb2b7ba483957710ad771e7d73eaab01a419", "42f7a2309e192e939213e3d6e8ca11a592f9ab9e"]
   },
   "v23_pinned_lf_sha256_after": {
    "tests/v23/test_v23_q0_round.py": "c16fef76d0f5f45448736142bbab080f490f2ad53ff30a61145acc02b2c75ee7",
    "tests/v23/test_v23_rounds.py": "e2922d9e8f2784046fe2e0d97b24a5bae9ae97d4479e8f05f78758622a975f1b",
    "validation/v23/q0_round.py": "36be24327caa33efe8a7b03d6608c8c13f54c04a1b7ff341bd74b26253322c10"
   }
  },
  "SUPERSEDES": "Named seq-13 NOT_AUTHORIZED clauses, superseded for exactly this scope and no further: (1) 're-pinning or removing V23_PINNED' — superseded only for the three files in v23_pinned_lf_sha256_after, re-pinned to exactly those digests through the named patch; (2) 'any wiring other than the named patch' — SEQ14-PIN57-C.patch joins SEQ13-WIRING-R6.patch as named wiring (the stack v2.2.0 + R6 + seq-14 is what Seq13Wiring now requires); (3) 'adding a module to NOT_CHECKERS_V23' — superseded only for the five files named in NOT_CHECKERS_V23 above; (4) 'a validation/v23 module without a registered, calibrated checker' — superseded only for validation/v23/observe.py and the four ground_truth files, each ruled a non-checker here with always-run drift pins. It also discharges, for f5_gate and released_evidence, the registration mandate of owner ruling 2026-11-22 §D, and records the ruled exception to it for f5_recorder while the NO_OBSERVATION_AUTHORITY condition holds. Every other seq-13 clause stands unchanged.",
  "REMAINS_RED": "This entry relaxes no checker and flips no wait: the three registered-but-uncalibrated states stay exactly as they are and stay visible — b1_bindings (waits on OD-B1B), currency_dag (waits on the P5-PROPOSAL currency decision), mutation (waits on the F5 cut-over). After the amendment the live Q0 round count is calibrated 56 of 59 (measured red-before 54 of 57 plus the two newly registered, calibrated checkers), Q0RoundV23's count test stays red on those three and on the still-unwritten round record, and --write stays refused until every rule holds. The Q0P-2 scope reds for the eight uncovered modules are the only reds this amendment removes, by covering or ruling every module, never by weakening the rule.",
  "NOT_AUTHORIZED": "landing this amendment (the agent developed and tested it; applying the patch on the branch and committing it, like committing this entry, is the owner's); publishing; tagging; writing or committing the round-v2.3 Q0 record (--write stays refused while any rule fails); registering f5_recorder, or wiring observations into any gate, without a new exact owner ruling; removing or weakening tests/v23/test_v23_unregistered_checkers.py while f5_recorder or the ground_truth files stay outside the registry; touching b1_bindings, currency_dag or mutation calibration states; deciding OD-B1B, the P5-PROPOSAL currency wait or the F5 cut-over (each stays the owner's); any edit of the 18 sealing-gated test files, of GATED or of tests/v2/test_sealing_gate.py; rewriting any v2.2 or earlier record or ledger entries 1-13; any change of this draft after it is committed (a later ruling is a new draft file); any wiring other than SEQ13-WIRING-R6.patch plus SEQ14-PIN57-C.patch; adding any further module to NOT_CHECKERS_V23",
  "EVIDENCE_REVIEWED": "docs/v2.3/evidence/PIN-57-MODULE-ROLES.md (identities, callers, trust boundaries, negative tests; measured at bc8668f0, re-verified at 466c9f94 and 50960ffa — the before-blobs above are byte-identical); docs/v2.3/drafts/PIN-57-AMENDMENT-CANDIDATES.md (Candidate C and the 2026-11-26 ground-truth addendum); the proof transcripts docs/v2.3/drafts/SEQ14-PIN57-C-PROOFS/ (red-before, green-after with the exact surviving reds, q0_round --check before/after, the v2.2 replay PASS, and the calibration of the two newly registered checkers against their committed fixtures)"
 },
 "subject_to": "ledger seq 13's subject_to in full (W1-DESIGN.md §2.6 and §11 gate 3 as amended by Q0-1-V23-ROUND.md and Q0-1-R5.md), unchanged; and owner ruling 2026-11-26 §3: f5_recorder stays outside the registry only while observation data cannot serve as qualification authority — the condition is load-bearing and its always-run pin (tests/v23/test_v23_unregistered_checkers.py) may not be removed or weakened while the retention stands",
 "cost": "USD 0"
}
```

canonical ruling digest: `3cc825e1d6de8d051e8e4ed4ecf4403c865f9a177a2529757f2d949b6625c2cc`. It is the sha256 of
`json.dumps({seq, id, decision, subject_to, cost}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)` in UTF-8.
`python3 -P validation/v23/ledger_digest.py docs/v2.3/drafts/LEDGER-SEQ-14-DRAFT.md` recomputes it from the file.

## Digest table (measured; the owner verifies these at issuance)

Before-blobs measured at HEAD `50960ffa1f398a0ae112a38f70540d65d7bbfa33`; after-blobs measured by applying
`SEQ14-PIN57-C.patch` (sha256 `ed7a55d89368707dc1897d191a6e1fdd70ad8f5b70ab74ffec9dc21e4236baac`, LF == raw) in a
worktree and hashing (`git hash-object`), 2026-11-26.

| file | blob sha1 BEFORE | blob sha1 AFTER | change |
|---|---|---|---|
| `tests/v2/sealing_gate.py` | `f6b64b5264fb55a6863145bc7722ec869d1f2535` | `90adf82e49fce5204c472721cc0326ff0b3e5934` | V23_PINNED: 3 digests re-pinned + seq-14 comment; nothing else |
| `tests/v23/test_v23_q0_round.py` | `8d518bf8f392300a6d5e280d74f6a2f3e360a5d6` | `2f01c39d2d4ab9af266eca77e159c0a295906f37` | :219 `56`→`58`; :223 `"56 of 57"`→`"58 of 59"`; Q0Record.setUpClass +2 synthetic rows, counts 59 |
| `tests/v23/test_v23_rounds.py` | `a8eb0a0c7b3ae6c1644a854338ef3e4cae8099e4` | `83aafa51cdc7984c6918b8c836671726af1079b8` | SEQ14_PATCH_REL/SEQ14_DRAFT_REL; `wired_sealing_gate(*patches)`; Seq13Wiring requires the seq-13+seq-14 stack |
| `tests/v23/test_v23_seq13_wiring.py` | `5891086854f9e98b8b01e639aadd79b497f9cb93` | `fa51360733e20e115475fd77dc73cf9afe3fb69b` | WiringR6 wired = R6+seq-14; seq-14 patch file-set + draft-sha pins; seq-13-alone-skips-nothing |
| `tests/v23/test_v23_unregistered_checkers.py` | — (new file) | `4b20886ae8b1ad3677e484f2e8a97ade575189b5` | always-run drift pins (recorder calibration, unwired observations, ground-truth absence, the split) |
| `validation/v2/checker_calibration.py` | `56bf4453ad02aa907e39c4b8e0942c3387775915` | `e9736ee7d41388030bf67db066c393e105adb7bd` | `REGISTRY += [_f5_gate, _released_evidence]` (57→59); `V23_CHECKERS = (_f5_recorder,)`; comments rewritten |
| `validation/v23/q0_round.py` | `d74edb2b7ba483957710ad771e7d73eaab01a419` | `42f7a2309e192e939213e3d6e8ca11a592f9ab9e` | `NOT_CHECKERS_V23` += observe.py + 4 ground_truth files, dated comments with authority + promotion clause |
| `closure-evidence/v2/cycle2/RELEASE-DECISIONS.json` | `a33f2197bfcb00d064cb74e169b246343de77840`* | ________ (owner) | owner appends entry seq 14 (append-only, CIGOV-R1) |

*The ledger blob above is the one the candidates document measured at 466c9f94; it is unchanged at 50960ffa (verified).
The two registered checkers' fixtures are untouched: `f5_gate.json` `912daa2d1d080d9bfc1c608d473cff261ab3369d`,
`released_evidence.json` `f978ebfb72c3935a18ab4cfc580d29baedb8a0d6`; `f5_recorder.json`
`cfa3798b476b79e53189ad3ed385af8144d8e65b` (drift-pinned by the new always-run test).

## No-observation-authority proof (f5_recorder)

The retention of `f5_recorder` outside the registry stands on the measured fact that its observation data cannot
determine a qualification verdict as wired:

1. **No gate supplies the input.** `impact.classify` is called without `observations` by every gate and guard:
   `validation/v23/ci_gate.py:173`, `validation/v2/mutation.py:2855/2868`, `tests/v23/test_v23_rounds.py` `_f5_states`;
   no `.github` workflow passes `--observations` (grep 2026-11-26; the only consumer is `impact.py`'s own CLI,
   `validation/v23/impact.py:1577-1582`, documented "an input only").
2. **Even when supplied, never an acceptance basis.** An observation-based reuse carries
   `observation:<sha256>@<base>` with `evidence.authority` = `impact.OBSERVATION_AUTHORITY`, the
   `"none: the F5 recorder is approved for development only, not as a VERIFIED_REUSE authority …"` sentinel
   (`impact.py:136`, applied at `:1198-1200`); `ci_gate.reuse_problems` refuses the form without the sentinel
   (`ci_gate.py:143-145`); pinned by `tests/v23/test_v23_review1.py:308` (PROV-1).
3. **Owner ruling 2026-11-21** names the recorder a development tool, not a reuse authority (`observe.py:6-9`,
   `impact.py:30-31`).
4. **The condition is now pinned, always-run:**
   `tests/v23/test_v23_unregistered_checkers.py::UnregisteredCheckers.test_the_observations_input_of_the_engine_stays_unwired`
   goes red on any `observations=`/`--observations` wiring outside `impact.py` across `validation/`, `aisef2/` and
   `.github/`, and on any change of the authority sentinel away from `"none: ..."`. Its calibration drift pin
   (`test_f5_recorder_stays_calibrated_against_its_committed_fixture`) runs `cc.calibrate` on the committed fixture
   every suite run — closing PIN-57-MODULE-ROLES.md §5 fact 3 for the one checker that stays outside.

Wiring `--observations` into any gate re-opens Decision 2 for this module: registration/calibration or a new exact
owner ruling, per the ruling text above.

## What approval would and would not do

* It would let the owner (or the agent on the owner's explicit instruction naming this entry) apply
  `SEQ14-PIN57-C.patch` on the branch and append entry 14. The Q0P-2 scope reds (8 modules) end; `Seq13Wiring`,
  `Q0Wiring` and `WiringR6` hold over the stacked wiring; the new drift pins run on every suite.
* It would NOT make round v2.3's Q0 green: `b1_bindings`, `currency_dag` and `mutation` stay red (OD-B1B, the
  P5-PROPOSAL currency wait, the F5 cut-over — each the owner's), the live count is 56/59, and the round record
  stays unwritten (`--write` stays refused) until those clear. Measured in SEQ14-PIN57-C-PROOFS/.
* It decides nothing else: no publish, no tag, no record, no change to any v2.2 contract or fixture.

*Drafted 2026-11-26 under owner ruling 2026-11-26 §3 (development and testing authorized; landing not authorized).
This draft registers nothing by itself; every sha above is measured, and the owner's issuance must quote the
canonical ruling digest.*
