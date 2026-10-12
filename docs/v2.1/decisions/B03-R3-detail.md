# B-03 round 3 / WP detail — the 1,500-character bound is a bound on the statement, never on the evidence

Branch `v21r3/detail`, base `3dc827b`. Owner decision of 2026-10-12, item 5, quoted:

> Tôi chọn: giới hạn này chỉ áp dụng cho phần trình bày tóm tắt, không được làm mất bằng chứng cần để xác minh hoặc tái hiện lỗi.
> Giữ bản reproducer đầy đủ, đã che bí mật phù hợp, trong artifact có định danh và được ràng buộc vào evidence. Phần tóm tắt cần nêu điều kiện tái hiện, kết quả mong đợi/thực tế, dấu hiệu đã cắt và đường tham chiếu tới artifact.
> Nếu chưa có artifact đầy đủ, không được coi một đoạn bị cắt là reproducer đủ căn cứ để chặn story. Kiểm tra trường hợp thông tin quyết định nằm sau ký tự 1.500 và trường hợp nội dung chứa bí mật.

Sections: 1 reading, 2 what the code did (measured on `3dc827b`), 3 design, 4 alternatives rejected, 5 requirement to
test, 6 real versus simulated, 7 residual risks and what is not established.

## 1. Reading of the decision

1. The 1,500-character limit survives, but only as the size of the **journaled statement** (the `detail` of the
   `gate/check` row; it is also the developer's retry prompt). Nothing needed to verify or reproduce a finding may live
   *only* in a place that limit applies to.
2. The full reproducer is kept in an **artifact**: identified (a path in the run directory, a sha256, a size),
   secret-redacted, and **bound to the evidence** (the journal row names its sha256; the evidence manifest lists it).
3. The statement says: the conditions to reproduce (subject, stimulus), the expected and the observed result, **that and
   how much was cut**, and where the artifact is.
4. A cut fragment is never grounds to block. Without a preserved artifact there is no block.
5. The two cases the owner names are tests: decisive information *after* character 1,500, and content that holds a
   secret (including a secret that straddles the cut).

Where my reading is not literal: "the decisive information after character 1,500" is tested at the statement level
(no field of the statement can be evicted by another) and at the run level (a real run, a stimulus of 4,000+ characters).

## 2. What the code did (measured on `3dc827b`; `scripts/before_unit.py`, `scripts/before_product.py`)

* `detail` = `json.dumps({finding, severity, summary[:400], clause, verification, why[:300], anchor, anchor_why[:300],
  reproducer:{subject, stimulus, observable}}, sort_keys=True)[:1500]`: the slice is applied to the **encoded text**.
  Measured: a 3,000-character `stdin` makes the text exactly 1,500 characters, **invalid JSON** ("Unterminated string"),
  and the keys that sort after `reproducer` — `severity`, `summary`, `verification`, `why` — are gone, as is `subject`.
  Through `aisef run` the blocked row held 1,563 characters with no `verification` and no `why`. Nothing marks a cut.
  No test asserted `len(detail) <= 1500`.
* Two more defects found in the same function: a lone surrogate in a model's text (`json.loads('"\\ud800"')` yields one)
  is journaled as is and the journal line then fails to encode (`UnicodeEncodeError: surrogates not allowed`); and a
  reproducer with keys of mixed type raises `TypeError` in `sort_keys`.
* Where the full finding lived: the session stream (`sessions/*.jsonl`: the model's text, or OCR's `ocr_output`
  document — byte-redacted with the run's secrets) and `RUN.json` `sessions[].findings[]` (the finding with its
  verification and anchor; **unredacted**; written in the `finally` of `execute`, so a run that is killed has only
  `RUN.started.json`, the journal and the streams). The journal row holds only the cut statement and **no reference
  to either**: the link is "story + finding id + order of the sessions", not bound by any hash, and ambiguous when two
  findings of one review share an id.
* Secrets (measured with a secret in an OCR comment's reproducer, `AISEF_TEST_SECRET` in `client_env`): present in
  `RUN.json`, in the journal row **and in the developer's retry prompt**; absent only from the session stream. The
  stream is redacted on its bytes after the finder ran; the findings come from the in-memory document read *before*
  that. (The model finder reads its text *after* the stream's redaction, so a contiguous secret is already out.)
* `blocks()` decided from the in-memory `Verification` — the probe ran the *full* reproducer — while the journal kept
  only the cut text: a third party could not re-verify a block from the evidence.

## 3. Design

### 3.1 The statement (`review_verify.detail`) — bounded by construction

`detail(finding, v, anchored=None, artifact=None, secrets=())` returns one JSON object, always valid, always
`<= SUMMARY_MAX` (1,500) characters:

| field | content | bound (encoded characters of the string body) | evictable |
|---|---|---|---|
| `finding`, `severity`, `clause`, `verification`, `why`, `observed`, `anchor`, `anchor_why` | what decided the block | 60, enum, 40, 20, 160, 24, 24, 160 | never by another field; cut only at its own bound |
| `artifact` | `{path, sha256, bytes}` of the full statement, or `null` + `artifact_why` (120) | fixed by the type | never |
| `summary`, `reproducer.subject`, `.stimulus`, `.observable` | the conditions to reproduce, expected (`observable`), the finder's prose | what is left of 1,500 after everything above and a reserve for the markers, shared out smallest-first | cut at their share |
| `elided` | `{field: characters left out}` — present only when something was cut | reserve of 4 entries + 14 | — |

* A value that fits its share is stated whole (an object, as before). One that does not becomes the **prefix of its
  canonical JSON text** as a string, and `elided[field]` says how many characters were left out. `elided` is
  authoritative: a field it does not name is whole.
* Bounds are on the **encoding** (a quote is 2 characters, a control character 6), measured per character, so no
  input can inflate a field past its bound; the arithmetic is checked in the tests with the worst encodings.
* `observed` is the probe's verdict on the stated behaviour (`REFUTED`, ...): the probe protocol returns a verdict,
  not the observed values, so that is all the kernel has to state as "actual".
* The text is made encodable (a lone surrogate is written as its `\udXXX` escape, as `reproducer_contract` does for prose) and
  keys of other type than `str` are written as `<type>repr`: `detail` never raises.
* Secrets are removed from every string, **keys included, before anything is cut**: a secret straddling a bound cannot
  be half-leaked.

### 3.2 The artifact (`review_verify.preserve`)

* Path `review-findings/<story>.<attempt>.<index>.json` (index = position in the finder's list: two findings with the same
  id do not collide). One file per finding per attempt; **create-only** (an existing file is a refusal), written to
  `<name>.tmp`, `fsync`ed and renamed over (`os.replace`, as `runtime/sentinel.py`): a reader never sees half a file, and
  `*.json` never matches the temporary. A new directory, **not** `sessions/` (the budget and usage readers glob it
  for streams) and not `review/` (OCR's per-attempt work directories).
* Content: `{format, story_id, attempt, index, revision (the candidate the probe ran at), session (the finder's stream),
  redacted (how many secrets were replaced), finding (the whole finding as the finder wrote it, plus the kernel's
  `verification` and `anchor`)}`; ASCII JSON, sorted keys. `redacted: 0` means the file holds exactly the reproducer
  that ran; otherwise it is the run's reproducer with `[REDACTED]` where a secret was.
* Redaction uses the run's own list: the client environment values and the provider key (`kw["secrets"]`) and OCR's
  token — the list the session streams are redacted with.

### 3.3 Binding

1. **Journal**: the row's statement carries `artifact.sha256` and `bytes`; the journal is hash-chained, so the row
   binds the file. `gate/check` has a closed payload schema (a new key would be a journal format bump, §35), so the
   reference lives in the `detail` text, as the statement already did.
2. **Manifest**: `evidence_manifest` lists `review-findings/*.json`. A run directory without that directory yields
   exactly the manifest it always did (the glob is empty); `MANIFEST_FORMAT` is unchanged (precedent: `RUN.started.json`
   was added to the list without a bump). An older verifier refuses a newer run's directory by naming the files it
   does not know — the safe direction.
3. **`aisef run --verify`** (`review_verify.artifact_problems`, called from `verify.verify`): every review row that
   names an artifact must name a path inside `review-findings/`, a file that exists with the size and sha256 the row
   states, whose content is that story's and whose finding id starts with the row's. Missing, altered or mismatching
   is REFUTED, with the row's seq. A *blocking* row that names no artifact is a **problem** when it says
   `artifact: null` (this release never writes one) and a **note** when it has no `artifact` key at all (a run of an
   earlier release: those verdicts are not changed).

### 3.4 A block needs its evidence

`Reviewer.review` preserves each finding's artifact before building its row. If the finding **would block**
(`blocks()` said so) and the artifact could not be preserved (write fails, the file exists, the finding cannot be
serialised), the review is **refused**: `CapabilityUnrunnable` — owner ENVIRONMENT, "every finding discarded", the
reason in the journal's `provider/result` row. A finding that would not block and cannot be preserved is journaled
with `artifact: null` and `artifact_why`, non-blocking as it already was.

Why refuse rather than "report non-blocking": under `fix-loop` the review's whole purpose is to act on confirmed,
anchored findings. A write failure would otherwise turn every confirmed defect into a pass — a fail-open on an
environment fault. This module's other answer to "the review's evidence cannot be established" is the same one
(`_unchanged`: "every finding discarded"; OCR coverage INDETERMINATE under `fix-loop`). The cut fragment is never what
blocks; the story fails for an environment reason and is retried through the taxonomy's ENVIRONMENT limit.

### 3.5 Secrets everywhere the finding is persisted

The statement, the artifact and `RUN.json`'s `sessions[].findings[]` are redacted from the same list. The probe still
runs the in-memory, unredacted reproducer (a redacted one would reproduce something else).

## 4. Alternatives rejected

* **Raise the limit / slice the encoded text more carefully.** Any limit evicts something; the owner's rule is that the
  limit is not where evidence lives.
* **Keep the full reproducer only in `RUN.json`.** Exists only when the run ends, unredacted, not referenced by the
  row (measured above).
* **Put the artifact under `sessions/`.** `client.Budget` and `usage` read every `sessions/*.jsonl` as a model
  session's stream.
* **A new key on the `gate/check` payload.** Format bump of the journal (§35).
* **"Reported but non-blocking" when the artifact cannot be written.** Fail-open (3.4).
* **One file per finding id.** Ids are model-chosen, unbounded, not unique within a review, not file-name safe.


## 5. Requirement to test

| requirement | test (file) |
|---|---|
| the statement is valid JSON of at most `SUMMARY_MAX` for any finding (100,000-character fields, unicode, control characters, nested, keys that are not strings) | `TheStatementIsBoundedByConstruction.test_the_bound_holds_for_a_seeded_sweep_of_adversarial_findings`, `...test_the_worst_encoding_of_every_decisive_field_still_leaves_the_elastic_fields_room` (statement) |
| decisive information after character 1,500 is not lost: what decided the block survives a stimulus of any size | `...test_what_decided_the_block_is_there_whatever_the_size_of_the_stimulus`, `...test_one_huge_field_evicts_no_other`, `...test_several_huge_fields_share_what_is_left_and_all_are_marked`, `...test_each_decisive_field_is_cut_at_its_own_bound_and_marked_exactly` (statement); product: `test_the_blocked_row_is_valid_json_within_the_bound_and_says_what_decided_it` |
| the statement states conditions, expected, observed, the cut and the artifact | `WhatIsStatedAndHowItIsMarked.*` (statement); product: `test_the_statement_names_the_artifact_and_it_is_the_file_with_that_digest` |
| a cut is marked with the exact number of characters left out | the `elided` assertions of the same tests; `test_the_marker_counts_characters_of_the_text_not_of_its_encoding` |
| a secret is not in the statement, and not half of it at the cut | `SecretsAreOutBeforeAnythingIsCut.*` (statement: 100 offsets around the stimulus's cut, 3 decisive fields around their bounds) |
| text with no UTF-8 form, keys that are not strings, non-JSON values, absurd nesting never raise | `TextThatIsNotUtf8AndKeysThatAreNotStrings.*` (statement) |
| the full finding is kept whole, redacted, identified, create-only, written whole before visible | `PreserveWritesTheWholeFinding.*` (artifact) |
| a failure to keep is a reason, never an exception | `...test_a_failure_to_keep_is_a_reason_and_never_an_exception`, `...test_the_file_is_whole_before_it_is_visible_and_a_failed_write_leaves_nothing_visible` (artifact) |
| the journal row binds the artifact; `--verify` refuses missing, altered, mis-pointed, outside the directory, a blocking row with none | `ArtifactProblems.*` (artifact); product: `test_an_altered_artifact_is_refuted_by_the_manifest_and_by_the_row`, `test_a_removed_artifact_is_refuted`, `test_an_artifact_rewritten_with_the_manifest_made_again_is_still_not_the_file_the_row_binds`, `test_without_a_manifest_the_row_still_binds_the_artifact` |
| the manifest lists the artifacts; a directory with none lists what it always did | `ManifestBindsTheArtifacts.*` (artifact); product: `test_the_manifest_lists_the_artifact_and_the_run_verifies`; failclosed: `test_a_run_that_kept_no_artifact_has_the_manifest_it_always_had` |
| a finding that would block and cannot be preserved refuses the review; a cut statement is never what blocks; a finding that would not block is reported with why it has no artifact; advisory refuses nothing | `ReviewerKeepsTheEvidence.*` (artifact); failclosed (`aisef run`): the four tests of `WithoutItsArtifactAFindingNeverBlocksAndTheStoryIsNeverCommittedOnIt` |
| the run's secrets (client environment, provider key, OCR token) are out of the statement, the artifact, `RUN.json`, the journal and the retry prompt | `ReviewerKeepsTheEvidence.test_a_blocking_finding_blocks_on_its_artifact_and_the_row_names_it`, `...test_the_finders_own_token_is_a_secret_of_the_run_too`, `...test_the_id_that_names_the_gate_row_carries_no_secret_either`; product: `test_the_secret_is_in_nothing_the_run_persisted_for_its_reviewers_findings`, `test_the_developer_is_told_the_finding_as_stated_on_its_retry`, `test_the_record_keeps_the_finding_the_finder_made_with_the_secret_out`; model: `test_the_secret_is_in_none_of_the_run_s_files_and_the_run_verifies` |
| the developer's retry prompt still carries the finding, readable | product: `test_the_developer_is_told_the_finding_as_stated_on_its_retry`; the existing `test_v21_review_chain.FixLoop` |

Files: `tests/v2/test_v21_r3_detail_statement.py`, `..._artifact.py`, `..._product.py`, `..._failclosed.py`,
`..._model.py`. The product-path files run a real `aisef run` with a fake developer and a fake finder script.

### Existing tests changed (rule 5)

* `tests/v2/test_v21_kills3_T15a.py::StatementOfAFinding.test_a_confirmed_and_anchored_finding_is_stated_in_full` — the
  expected dict gains `"observed": v.observed`. Owner sentence: the statement must state "kết quả mong đợi/thực tế";
  every other key and value is asserted as before.
* `tests/v2/test_v21_authority_limits.py::OneDecisionPath.test_what_blocks_answered_rebound_or_not_asked_on_every_path_is_caught` —
  the two source anchors `whole` and `inner` are literal copies of the statement that builds a `Finding`; it now passes
  the artifact reference and the run's secrets to `detail` and names the id `fid` (redacted). No rule of the checker
  and no assertion changed: the checker passes on the real tree and still catches each edit.

## 6. Real versus simulated

* **Real**: the statement and artifact code; the journal (`format3`), the manifest, `--verify`; the real
  `cli_invocation` and `python_callable` probes executed on real git checkouts; the file-system behaviour of
  `preserve` (a directory that is a file, a missing run directory, `os.replace`/`os.fsync` failing through a patched
  `os` function only for the call); the measurement on the 10 older run directories found in the scratchpad.
* **Simulated**: the developer (a script), the finder (a script that writes OCR's documents), the provider (a
  transport stub); "the write fails with ENOSPC" in the `aisef run` failclosed test is the keeping function
  replaced (the real failures are in the unit file).
* **Linux guest**: see the report (`test_runs`): the new test files and the checks around them run in the Docker guest
  (real run, Python 3.14.8, no network).
* **Neither**: Windows, Python 3.11–3.13 — written for them (pathlib, bytes, `skipUnless(posix)` only for the
  shebang-script runs), not run here.

## 7. Residual risks and what is not established

* **`review/<story>.<attempt>/output.json` (the finder's own raw output, written by the OCR binary) keeps the secret
  verbatim and is not in the manifest.** Measured (`secret_in_review_work_files`). It is outside the functions this WP
  changes (`Reviewer._ocr`); redacting those files after the finder ran is three lines with `client.redact` — an
  owner/lead call (listed in `decisions_needed`).
* The session stream's redaction (`client.redact`) is on bytes: a secret with JSON-special characters, or split across
  two `text` events of the model finder, is not matched there. The statement, the artifact and `RUN.json` are redacted
  on decoded strings; the stream is not changed by this WP.
* A secret split across two strings of the reproducer (two argv elements) is not one string and is not matched.
* `observed` is the probe's verdict, not the observed values: the probe protocol (`Executed`) carries no more. A
  verifier re-running the artifact's reproducer at `revision` gets the values.
* `redacted: 0` means the file holds what was handed to the probe; for the model finder that text has already passed
  the stream's byte redaction. A reproducer that held a secret and was redacted would reproduce differently — the
  artifact says how many replacements were made.
* A structure nested deeper than 64 levels is kept as a marker (no probe grammar nests that deep; such a reproducer
  is refused as a contract and never blocks).
* A key collision after redaction or type normalisation is resolved by `<key>#<position>`; a literal key of that form
  at the same position would still collide. Not reachable from `json.loads` output with one secret.
* A temporary `*.json.tmp` left by a write that failed is not cleaned (no new delete site): the same
  (story, attempt, index) is never written twice within a run, and a leftover is not in the manifest.
* Artifacts written for findings of a review that was then discarded (the checkout changed during the verification)
  are kept and are in the manifest; no journal row names them.
* Docs that list the manifest's contents (`docs/v2.1/ANCHOR-THREAT-MODEL.md`, `USAGE-2.1.md`, `ADR-V2.1.md`) say "record,
  journal, streams, preflight": not edited here (shared documents).
* Not measured: behaviour with a real Open Code Review binary or a real model finder; only scripted ones.
