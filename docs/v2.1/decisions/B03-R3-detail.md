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

(Sections 5–7 below are completed with the measured results.)
