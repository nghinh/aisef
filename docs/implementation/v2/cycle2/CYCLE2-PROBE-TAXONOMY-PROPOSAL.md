# CYCLE-2 PROBE TAXONOMY PROPOSAL

**Status.** Planning artefact (owner's "CLOSE CYCLE-1 / PREPARE CYCLE-2 ARCHITECTURE ONLY", 2026-09-28). It designs — and
does not implement — the probe kinds that the capability-gap matrix shows LedgerLock needs, in the order the owner
set: `cli_invocation`, `file_artifact`, `process_effect`, richer `python_callable`, and `http_route` only if a measured
need appears (none does). Every kind is designed inside the frozen probe protocol (see the F5 report); the shared
discipline of §1 is what keeps a proof verdict a function of the immutable revision, the `ProductProofSpec` and the
capability identity, and of nothing else.

## 1. Shared discipline (every kind)

| property | mechanism | inherited from Cycle 1 |
|---|---|---|
| harness-owned, never developer input | the probe reads `spec.probe_input` (compiled from an approved contract) and a `RevisionRef`; no path, argv or file comes from the developer (invariant IX) | python_callable |
| fresh evaluation directory | one `TemporaryDirectory` per evaluation (the story's scratch when given): working directory, workspace files, bytecode cache prefix, protocol files; refused if it lies inside the checkout | P7-FINDING-001 correction |
| interpreter isolation | `-I -B -X pycache_prefix=<fresh>` on the command line; never an environment variable | P7-FINDING-001 correction |
| scrubbed environment | the allowlist of `_scrubbed_env()` plus pinned `LC_ALL=C.UTF-8`, `PYTHONUTF8=1`, `PYTHONIOENCODING=utf-8`, `PYTHONHASHSEED=0`, `TZ=UTC`, `HOME=<fresh dir>`; no shell (`shell=False`, argv exec) | python_callable |
| owned process range | every subprocess starts in the story's range (`on_range`); signals read from the controller's ledger only (§9.3) | P4, V2-003 |
| protocol discipline | READY / DISPATCHED / RESULT lines with a per-evaluation nonce; the subject's own output is captured, never a protocol channel; pump-completion barrier (§9.4) | V2-006 |
| no clock read for control | the only times a probe reads are the observation window's deadline (harness) and none inside a verdict; timestamps in stimuli are data | NO_TIME_IN_PROJECTIONS, python_callable |
| observation classes registered | `ProbeMetadata.observation_class` decides what a spec asks; unknown → `UNSUPPORTED` → `INVALID_SPEC` at admission (check 9) | PROBE-META-1 |
| calibration before admission | a `ProbeCapabilityCalibration` per (id, digest, class) with a positive and a negative fixture; `SpecFalsifiabilityEvidence` per qualified spec | F5 §9.1 |
| digest | sha256 over the probe's sources (LF-normalised); a change is a new digest, a new capability identity, new calibrations | python_callable |

Placeholders: a stimulus may write `<ws>/name` for a file the harness creates in the evaluation directory; the harness
substitutes the absolute path before dispatch. No other substitution exists; `<ws>` is the only token.

## 2. `probe.cli_invocation`

**Subject.** `kind = cli_invocation`, `locator = "<module>:__main__"` (a runnable module of the revision; the harness runs
it as `runpy.run_module(module, run_name="__main__")` after resolving the module *inside* the revision) — or
`"<module>:<callable>"` for an argparse-style entry function invoked with `argv`. Console-script names are not accepted
(they resolve through the environment, not the revision).

**Stimulus.**
```json
{"argv": ["verify", "<ws>/ledger.jsonl"],
 "stdin": null,
 "workspace": {"ledger.jsonl": {"text": "...", "newline": "\n"} , "batch.json": {"bytes_hex": "..."}},
 "pre": [{"argv": ["apply", "--batch", "<ws>/batch.json", "<ws>/ledger.jsonl"]}]}
```
`workspace` files are written byte-exactly (text with an explicit newline, or hex bytes). `pre` is an ordered list of
invocations of the *same subject* that build the state the criterion presupposes ("a fresh JSONL written via the
product"); each must exit 0 or the observation is `REFUTED` with the failing pre-step named in `detail`.

**Observable (classes).**
- `exits`: `{"exit_code": 2, "within_s": 30}`
- `exits_streams`: adds `"stdout": ""` (exact bytes) or `{"contains": [..]}`, and `"stderr": {"lines": 1, "first_word": "verify", "contains": ["ok"]}` or `{"regex": "^verify .*\\bok\\b"}`; prose matching is not offered
- `exits_files`: adds `"files": {"<ws>/snap.json": {"sha256": "…"} | {"equals_before": true} | {"absent": true}}`
- `blocks`: the invocation must not return within the window (the window expiry is SATISFIED)

Expired window: `REFUTED` for the three `exits*` classes, `SATISFIED` for `blocks` (§9.2, no default).

**Harness preconditions.** the interpreter launches under `-I`; the evaluation directory is creatable and outside the
checkout; the protocol channel (a harness-owned result file) is writable.

**Subject absence.** the module does not resolve inside the revision, or resolves to a module with no `__main__`
semantics → `SUBJECT_ABSENT`; the contract's `subject_absence` decides (a prohibition "the CLI must not write to stdout"
is `REQUIRES_SUBJECT`).

**Enforcement.** `PARTIAL` (no OS sandbox: the weakest path is the subject's own code reaching the filesystem and the
network of the harness user). `FULL` is offered only when an OS-level sandbox capability is present in the RunSpec and
named; never assumed.

**Deterministic execution.** shared discipline §1; the working directory is the evaluation directory, never the
checkout; stdin is the stimulus or `/dev/null`; the subject's stdout and stderr are captured to files and compared as
bytes after the process has closed them (§9.4).

**ProductProofSpec impact.** none to the shape; `probe_id = "probe.cli_invocation"`, its digest; `semantic_hash` binds
argv, workspace bytes, pre-steps and the observable exactly.

**Capability identity.** `verified("probe.cli_invocation", <sources>, PARTIAL)`; the interpreter's digest is a separate
capability already in the RunSpec.

**Calibration.** per class, a fixture module `calib_cli.py` that exits with the shaped streams/files (positive) and its
one-line mutant (negative); both verdicts demonstrated; an always-0 or always-nonzero fixture pair is rejected because
`calibrate` requires contrast on both sides.

**SpecFalsifiabilityEvidence.** `controlled_product_mutation` on the reference LedgerLock implementation (a committed
fixture, not AISEF output): flip the exit code or the stderr prefix; the spec must observe `REFUTED`.

**Mutation strategy.** targets: argv assembly, workspace writer, pre-step ordering, stream comparison, expiry verdict,
absence detection; kill tests per class.

**Fault matrix (Q3).** interpreter absent (HARNESS_FAILED); evaluation dir uncreatable / inside checkout (HARNESS_FAILED);
subject writes a forged protocol line to stdout (ignored: the protocol is on the harness file); subject never exits
(SUBJECT_DEADLINE → class verdict); subject killed by a non-controller signal (NON_CONTROLLER_SIGNAL); controller stops
the range (ProbeInterrupted, no result); stale bytecode in the revision (unreachable: `-B` + prefix); stdout flood
(bounded capture, `REFUTED` if the shape is exceeded); Windows: CRLF in captured streams compared as bytes the spec
declares (`newline` in the observable, default `\n` exact).

**Platform-specific behaviour.** protocol channel: fd 3 on POSIX, a temp file with a completion marker on Windows;
`runpy` identical; exit codes from `SystemExit` normalised by the harness (an integer, `None` → 0, a string → 1 as
CPython does) and recorded verbatim.

**Sandbox / process ownership.** the story's process range; the evaluation directory is the range's scratch.

**Security boundary.** the subject runs as the harness user; the contract's argv and files are approved content;
network is not blocked below `FULL` — stated in `WEAKEST_PATH`.

**Evidence schema.** `probe/evaluated.record.result.detail` carries `{"argv", "exit_code", "stdout_sha256",
"stderr_sha256", "files": {…}, "pre": [...]}`; never read for control.

## 3. `probe.file_artifact`

**Subject.** `kind = file_artifact`, `locator = "path:<relative posix path>"` (a file or a directory of the revision).

**Stimulus.** `{}` for `exists` and `content`; `{"grep": "<regex>", "suffixes": [".py"]}` for `grep_count`.

**Observable (classes).** `exists` (`{"condition": "exists"}`), `content` (`{"sha256": "…"}` or `{"equals_text": "…",
"newline": "\n"}`), `grep_count` (`{"matches": 0}`). Expired window: `REFUTED` (a read that does not complete is not an
observation of presence).

**Reading rule.** content and matches are read from the **git object store at the revision SHA** (`git cat-file -p
<sha>:<path>` / `git ls-tree -r <sha>`), never from the working file: autocrlf, executable bits, editors and symlinks
cannot become authorities. Existence is the tree's, not the filesystem's. A locator that escapes the tree (`..`,
absolute, a symlink target outside) is `HARNESS_FAILED`.

**Subject absence.** the path is not in the tree → `SUBJECT_ABSENT`; a prohibition ("no forbidden import in the
package") declares `ABSENCE_IS_DECIDABLE` so an absent package decides the contract (NEG-2/NEG-3).

**Enforcement.** `FULL` (no subject code runs; the weakest path is git's own object store, whose identity is the
revision SHA).

**Capability identity.** `verified("probe.file_artifact", <sources>, FULL)`; git's binary digest is already a RunSpec
capability.

**Calibration.** per class: a fixture tree with and without the file / pattern; both verdicts.

**Mutation.** targets: path normalisation, tree escape refusal, regex application, suffix filter, count comparison.

**Fault matrix.** git absent (HARNESS_FAILED); revision not in the repository (HARNESS_FAILED, never SUBJECT_ABSENT); a
binary file under a text grep (skipped by suffix, recorded); case-insensitive filesystems (irrelevant: the tree is read,
not the filesystem); a path with a symlink component (refused).

**Evidence.** `detail` carries the blob SHAs read and the match locations (file, line) — never read for control.

## 4. `probe.process_effect`

**Subject.** `kind = process_effect`, `locator = "<module>:<Class>"` or `"<module>:<callable>"`.

**Stimulus.** `{"scenario": [step, …]}` with a closed step vocabulary:

| step | fields | meaning |
|---|---|---|
| `workspace` | `{files: {name: {text|bytes_hex}}}` | files written into the evaluation directory before anything runs |
| `construct` | `{args: [...], kwargs: {...}}` | `instance = Subject(*args)`; `<ws>/x` resolved; at most one instance |
| `call` | `{method: "append", args: [...], as: "r1"}` | call on the instance (or the subject callable when no instance); the result is bound to a name |
| `expect_raises` | `{method, args, exception: "ConflictError", attrs: {key: "k", batch_index: 1}}` | the call must raise that exception type name with the attribute values; anything else is `REFUTED` |
| `write` | `{path: "<ws>/l.jsonl", bytes_hex | text}` | out-of-band file write (tamper, truncation) |
| `edit_jsonl` | `{path, line: 17, field: "hash", value: "000…"}` | out-of-band edit of one JSON line's field |
| `subprocess` | `{argv: [...]}` under the same interpreter isolation | "a separate process opens the path" |
| `fault` | `{patch: "os.replace", raises: "OSError"}` | **DECISION-2**: a controlled in-process fault for the next `call` only, removed afterwards |

**Observable (classes).** `scenario_returns` (`{"returns": {"ok": true, "first_bad_index": null}}` of the last call, or
`{"returns_name": "r1", "equals_name": "r2"}` for equality between bound results), `scenario_raises` (the last step is
`expect_raises`), `scenario_files` (`{"files": {"<ws>/l.jsonl": {"sha256"|"equals_before": true|"line_count": 3|
"final_byte": "\n"|"jsonl": {"line": 0, "field": "prev_hash", "equals": "GENESIS"}}}}`). Expired window: `REFUTED`.

**Harness preconditions.** as cli_invocation; the scenario interpreter's own sources are part of the probe digest.

**Subject absence.** the class or callable does not resolve inside the revision → `SUBJECT_ABSENT` before any step runs;
a method missing at `call` time is `OBSERVED` + `REFUTED` (the subject exists and does not offer the behaviour).

**Enforcement.** `PARTIAL` (as cli_invocation).

**Deterministic execution.** all steps run in one harness process in declared order; no step reads a clock (a `ts` is
stimulus data); the workspace is fresh; results are serialised through the same JSON rule as python_callable (`returned`
or `returned_unserializable` — a class that needs bytes says `bytes_hex`).

**ProductProofSpec impact.** none to the shape; `semantic_hash` binds the whole scenario.

**Calibration.** per class, a fixture module with a small stateful class (append/verify over a file) and its mutant.

**SpecFalsifiabilityEvidence.** `controlled_product_mutation` of the reference implementation per spec (e.g. drop the
`fsync`, skip the `rid` lookup) — the spec must refute.

**Mutation.** targets: step dispatcher, placeholder substitution, `expect_raises` attribute comparison, `edit_jsonl`,
file observables, the `fault` patch scope (must not leak past its call).

**Fault matrix.** every cli_invocation fault, plus: a step names an unknown kind (UNSUPPORTED → INVALID_SPEC, at
admission where possible); the subject swallows the fault (`OBSERVED` by the file observable); a subprocess step leaves
a process (the range's residual, never the probe's business); an exception in a non-final step (`REFUTED`, the step
named).

**Security boundary / ownership / evidence.** as cli_invocation; `detail` carries the step trace with per-step outcomes.

## 5. `probe.python_callable` extensions (new digest)

- `returns_bytes`: `{"returns_bytes_hex": "…"}` — the harness hex-encodes a `bytes`/`bytearray` result; anything else is
  `REFUTED`.
- `equals`: `{"equals": "GENESIS"}` over a **non-callable** subject (a constant): the harness resolves the attribute and
  compares its JSON form; a callable subject under `equals` is `UNSUPPORTED`.
- `workspace` stimulus: `{"workspace": {...}, "args": ["<ws>/empty.jsonl"]}` — fixture files for a one-call probe.
- `raises` gains optional `attrs` (as `expect_raises`).

Existing classes keep their meaning; the digest changes, so Cycle-2 calibrations cover all classes again.

## 6. `http_route` — not proposed

No measured need (0 of 77 criteria; the workload's requirements exclude a listener). Deferred with its trigger.

## 7. DESIGN-CHECK-1 — the protocol channel of a subject that owns stdout

`cli_invocation` and `process_effect` subjects may write to stdout. The python_callable harness puts its protocol on
stdout with a nonce; that is safe there because the subject's prints are captured before the RESULT line. For a CLI
whose stdout *is* the observable, the protocol must not share the stream. The proposal: the harness opens a dedicated
channel (fd 3 on POSIX inherited by the harness process only; on Windows a temp file whose completion is a final marker
line), writes READY/DISPATCHED/RESULT there with the nonce, and the reader applies the pump-completion barrier of
V2-006 to that channel. The Windows path must be shown equivalent under every scheduling of exit and file close
(§9.4) before Q1 accepts the probe; Q3's FM2-CLI-STREAM family holds the cases.
