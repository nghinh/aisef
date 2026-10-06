"""V2.1 Q5 corpus changes (owner B-03d, RELEASE-DECISIONS seq 5): every q5.CORPUS item whose expectation 2.1 changed or
added, traced to the approved requirement and decision, to the commit that changed the behaviour and to the tests that
prove it — data the B-03d ruling reads. Nothing here is executed and nothing is written.

Measured at dc9774f with this lane's q5.py: every item recorded and replayed in temporary directories as
tests/v2/test_p9_reproduction does (never `q5 --record`), under this tree's aisef2 and under aisef2 materialised at
v2.0.0 (c2_orchestration_repair.materialise); the change attributed under aisef2 at 919a271 and at 91a8968. 2.0's corpora
(closure-evidence/v2/Q5, cycle2/Q5, cycle2/Q5-FINAL, release/Q5-RC1, release/Q5-RC2) stay as recorded.
"""

V2_0_0 = "ca2631374602da45dae75b7f6907ff4729d0b2f7"   # tag v2.0.0
V21_38 = "91a89684e6c5a3ed7f2cf5fc52ef955d3a661cde"
V2_007 = "919a271ecfca246381b1de036a874f3b6935c0be"
V21_37 = "06d4e62c0b0666506cd95d663dfa8d3300e060a4"
RC2_CORPUS_REL = "closure-evidence/v2/release/Q5-RC2/CORPUS.json"

DECISION = ("docs/v2.1/STATUS.md §2 row B1: 'PRESERVE chỉ kiểm sau merge (V21-38)', fixed by 91a8968; docs/v2.1/ADR-V2.1.md ADR-4",
            "owner B-03d approval, closure-evidence/v2/cycle2/RELEASE-DECISIONS.json seq 5 (AISEF_V2_1_B03_REQUALIFICATION_ROUND): "
            "'a ruling naming 2.1's behaviour changes and a new Q5 corpus; 2.0's corpus, rulings and evidence kept'")

#: quoted from RC2_CORPUS_REL (items / coverage "post-merge-regression"); the failure from its corpus/post-merge-regression.json
RC2_POST_MERGE_REGRESSION = {
    "source": RC2_CORPUS_REL, "item": "post-merge-regression",
    "outcomes": {"S0": ["COMMIT"], "S2": ["ROLLBACK"]}, "model_calls": 4, "tool_calls": 2, "events": 143,
    "ledger_digest": "a21b7af5013b0fabe882c762ef050a070fa1a0bd2c7a57d765ccac7f5eb68f7f",
    "coverage": ["merge path", "post-merge path", "PRESERVE re-proof", "rollback path", "two stories"],
    "failure": {"seq": 134, "story_id": "S2", "code": "POST_MERGE_REGRESSION", "owner": "INTEGRATION", "retryable": False,
                "detail": "post-merge C0: POST_MERGE_REGRESSION"},
}

CHANGES = {
    "developer-regression-at-candidate": {
        "item": "developer-regression-at-candidate", "replaces": "post-merge-regression",
        "scenario": "two stories: S0 introduces C1 (add) and preserves C0 (sub), and commits; S2's developer answers C2 (mul) "
                    "with a candidate that also breaks sub — 2.0's post-merge-regression stream, S2's answer given again on the retry",
        "expectation_2_0": RC2_POST_MERGE_REGRESSION,
        "expectation_2_1": {
            "outcomes": {"S0": ["COMMIT"], "S2": ["RETRY", "ROLLBACK"]},
            "model_calls": ["DEVELOPER_IMPLEMENT S0", "REVIEWER_REVIEW S0", "DEVELOPER_IMPLEMENT S2", "DEVELOPER_IMPLEMENT S2"],
            "failures": [{"story_id": "S2", "code": "CONTRACT_UNSATISFIED", "owner": "DEVELOPER", "retryable": True,
                          "detail": "proof of C0: CONTRACT_UNSATISFIED"}] * 2,
            "s2": "S2:proof:C0 fails at each candidate; the retry's request carries prior_failures [CONTRACT_UNSATISFIED]; "
                  "S2 is never reviewed, merged or re-proved after a merge",
        },
        "cause_commit": V21_38,
        "requirement": ("docs/architecture/AISEF-V2-ARCHITECTURE-RFC.md §10.3: CANDIDATE x UNSATISFIED, any admitted role — the "
                        "implementation does not meet the contract — owner DEVELOPER",
                        "RFC §22.1: CONTRACT_UNSATISFIED, DEVELOPER, RETRYABLE",
                        "RFC §26: after merge every PRESERVE obligation of prior stories the merge could affect is re-proved; "
                        "a regression there is INTEGRATION's — kept for what the merge itself changes (post-merge-integration-regression)"),
        "decision": DECISION,
        "behaviour_tests": (
            "tests.v2.test_p9_reproduction.MultiStory.test_Q5_13_a_regression_the_developer_made_is_found_at_the_candidate_retried_and_never_merged",
            "tests.v2.test_v21_orchestration.PreserveAtCandidate.test_a_regression_the_developer_made_is_the_developer_s_and_never_merged",
            "tests.v2.test_v21_orchestration.PreserveAtCandidate.test_a_retry_that_repairs_it_commits",
            "tests.v2.test_c2_orchestration_conformance.ReproofOfAnotherKind."
            "test_a_regression_of_the_prior_spec_of_another_kind_is_the_developer_s_at_the_candidate_and_never_merged",
        ),
        "measured": {
            "2.0 item under aisef2 v2.0.0 and 919a271": "COMMIT / ROLLBACK, 4 calls (DEV, REV, DEV, REV), 143 events, "
                                                         "POST_MERGE_REGRESSION INTEGRATION at seq 134; replay GREEN (as release/Q5-RC2)",
            "2.0 item under aisef2 91a8968 and dc9774f": "S0 COMMIT, then EXTRA_MODEL_CALL: the script has no DEVELOPER_IMPLEMENT answer for "
                                                         "request 4; CONTRACT_UNSATISFIED DEVELOPER retryable at seq 109 'proof of C0'",
            "this item under dc9774f": "COMMIT / RETRY, ROLLBACK, 4 calls, 154 events, failures at seq 109 and 145; replay GREEN",
            "this item under aisef2 v2.0.0": "S0 COMMIT, then EXTRA_MODEL_CALL: the script has no REVIEWER_REVIEW answer for request 4 "
                                             "(2.0 reviews and merges S2's candidate)",
        },
    },
    "post-merge-integration-regression": {
        "item": "post-merge-integration-regression", "keeps_coverage_of": "post-merge-regression",
        "scenario": "two stories as above; S2's candidate is clean (mul only) and, right after S2's developer answer, main moves under "
                    "it: somebody else lands a sub that returns a + b (ORCH_9; q5._LandsAfter for the named story)",
        "expectation_2_0": RC2_POST_MERGE_REGRESSION,
        "expectation_2_1": {
            "outcomes": {"S0": ["COMMIT"], "S2": ["ROLLBACK"]},
            "model_calls": ["DEVELOPER_IMPLEMENT S0", "REVIEWER_REVIEW S0", "DEVELOPER_IMPLEMENT S2", "REVIEWER_REVIEW S2"],
            "failures": [{"story_id": "S2", "code": "POST_MERGE_REGRESSION", "owner": "INTEGRATION", "retryable": False,
                          "detail": "post-merge C0: POST_MERGE_REGRESSION"}],
            "s2": "S2:proof:C0 holds at the candidate (V21-38's row); S2:post-merge:C2 holds and S2:post-merge:C0 fails at the "
                  "merged revision; the merge is rolled back",
        },
        "cause_commit": V21_38,
        "requirement": ("RFC §26: after merge the story's obligations MUST be re-proved at the merged revision, together with every "
                        "PRESERVE obligation of prior stories the merge could affect; a regression is owner INTEGRATION",
                        "RFC §10.3: POST_MERGE x UNSATISFIED, any role — a regression after merge — owner INTEGRATION",
                        "RFC §22.1: POST_MERGE_REGRESSION, INTEGRATION, NOT_RETRYABLE"),
        "decision": DECISION + ("docs/v2.1/STATUS.md §2 row B2: the integrated tree re-checked when the target branch moves — ORCH_9",),
        "behaviour_tests": (
            "tests.v2.test_p9_reproduction.MultiStory.test_Q5_12_a_two_story_run_with_a_post_merge_regression_reproduces",
            "tests.v2.test_p6_orchestration.Orchestration."
            "test_ORCH_9_and_10_a_post_merge_regression_of_a_prior_PRESERVE_obligation_is_INTEGRATION_and_rolled_back",
        ),
        "measured": {
            "this item under dc9774f": "COMMIT / ROLLBACK, 4 calls (DEV, REV, DEV, REV), 151 events, POST_MERGE_REGRESSION INTEGRATION "
                                       "at seq 142; replay GREEN",
            "this item under aisef2 v2.0.0": "the same outcomes, calls and failure (seq 134), 143 events: without the candidate's C0 "
                                             "proof (8 events) that V21-38 adds; replay GREEN",
        },
    },
}

#: the other eleven 2.0 items, measured the same way: outcomes, failures, gate rows, event and tool counts and the
#: assertConsumed result equal under both kernels, replay GREEN under each — no expectation changed
UNCHANGED = {
    "identical_up_to_kernel_identity": ("normal-completion", "retry-then-commit", "review-finding-rollback", "pre-satisfied",
                                        "security-finding-rollback", "developer-outage-rollback"),
    "identity_only": {
        "items": ("cli-proved-story", "cli-refuted-then-commit", "file-artifact-prohibition", "scenario-proved-story",
                  "bytes-returning-python-callable"),
        "differing": "every request hash; plan/frozen plan_hash; probe/evaluated probe_digest, spec_id, semantic_hash, record_digest; "
                     "proof/verified spec_id, semantic_hash; the probe process-range names, which carry the spec id",
        "probe_digests_by_kind": {"cli_invocation": ("d42449fd8e3a", "330ae4a88cc8"), "file_artifact": ("31465b73cbe2", "be1485d12a4d"),
                                  "process_effect": ("815e4c865274", "409c41aea16f"), "python_callable": ("b1f25878d350", "0821c14651a9")},
        "cause_commits": {V2_007: "V2-007: a probe's digest is its capability digest (all four; file_artifact 31465b73cbe2 -> 46737ca1c479)",
                          V21_37: "V21-37: file_artifact python_imports, capability version 2 (46737ca1c479 -> be1485d12a4d)"},
        "decision": ("ARCHITECTURE-EXCEPTION-V2-007 approved: RELEASE-DECISIONS seq 4 (AISEF_V2_1_B01_ARCHITECTURE_EXCEPTION_V2_007)",
                     "docs/v2.1/STATUS.md §2 row B3 (V21-37)"),
    },
}
