# H-CONTEXT-AUTHORITY-001 — a general context-authority correction (DESIGN ONLY, not implemented)

**Status: OWNER_CONTEXT_DESIGN_DECISION_REQUIRED.** Owner ruling 'AISEF V2 — ATTEMPT-4 EVIDENCE FREEZE + RELEASE NO-GO +
MEASURED REMEDIATION DESIGN' (2026-10-03) §D. Nothing here is implemented; no provider was called; no LedgerLock run,
Q4 or Q5 was started.

Measured inputs: `closure-evidence/v2/cycle2/H-CONTEXT-AUTHORITY-001.json` (the finding, OPEN) and
`closure-evidence/v2/cycle2/DEVELOPER-CONFINEMENT-GAP-001.json` (measured while freezing attempt 4; named separately).
Method: six read-only investigators, three independent designs (minimal change; enforcement first; evidence and identity
first), one judge, two adversarial skeptics; every load-bearing claim below was re-measured by the main loop or by at
least two agents. **[M]** = measured, **[I]** = inferred. One process breach is reported, not hidden: one designer ran
`opencode --version` once against the rule "never execute opencode". It started no session and called no provider
(verified read-only: no OpenCode session was created after the run ended — the last is 01:49:12Z — and the OpenCode log
has no line after 02:02:37Z); no conclusion here rests on that call.

## 1. The problem, generically

A developer agent may need arbitrary source code from a repository, but stale or generated prose must not silently become
competing product authority against the frozen Requirements and the approved BehaviorContracts. The truth is already an
architecture rule: RFC invariant I, "Only frozen requirements and approved behaviour contracts define product truth.
Authority derives from where an artefact was admitted, never from what it claims about itself"
(`docs/architecture/AISEF-V2-ARCHITECTURE-RFC.md:144`, frozen as F10). Its four mechanisms
(`docs/implementation/v2/INVARIANTS-V2.md:9-12`) govern contract approval, compilation and kernel control — **none governs
what the developer is given or can read** [M]. Composing the developer's context is the harness's job: the kernel
`Developer` protocol passes only `(story_id, criteria, checkout)` (`aisef2/orchestrate/adapters.py:50-51`) [M].

Attempt 4 shows two distinct defect classes:

| Class | What happened | Where | Measured |
|---|---|---|---|
| **A — in-workspace authority** | non-authoritative prose in the workload repository both **introduced** the defect and **blocked** its correction | the developer's own checkout | STORY-01-01 attempt 1 read `_bmad-output/epics.md` (#12) and `EXPERIENCE.md` (#15), then wrote the four-field delete (#26); STORY-04-02 attempt 3 stated the root cause (#237) and stopped, citing the V1 story write-scope guard (#241) |
| **B — host reach** | the developer's bash reaches the whole host: the framework checkout (reference implementation, acceptance oracle, probe source), the kernel's probe scratch (`request.json` = hidden stimulus), the live kernel journal, the workload's source repository | outside the checkout | DEVELOPER-CONFINEMENT-GAP-001 facts 1-11 |

Class A happened in sessions whose adoption step never left the workspace, so an in-workspace correction is necessary.
Class B makes it insufficient against a hunting developer.

## 2. The approaches against the owner's criteria

| | 1. Prompt-only hierarchy | 2. Model-visible filesystem policy (client permissions) | 3. Authoritative-context manifest bound into RunSpec | 4a. In-place sparse view | 4b. Exported view + transplant | 5. Combination 3+4b (+ confinement) |
|---|---|---|---|---|---|---|
| **Enforceability** | none — failed three times: attempt 2 (`c2_p9.py:72-75`), attempt 3 "historical context only" (`5c7c5a6:c2_p9.py:235-240`), attempt 4 "authoritative specification … and by nothing else" (`c2_p9.py:294-298`) then #12→#26 [M] | file tools only | a declaration; enforceable only with an output-side filter | default exposure only | closes class A inside the workspace | A closed in the workspace; B needs confinement |
| **Bash/git bypass** | n/a | **yes**: OpenCode 1.18.31 checks `external_directory` for a fixed command set only; a global plugin rewrites bash before the parse; `git show <sha>:path` needs no outside path; 0 of 34 evaluations concerned the 28 framework reads [M] | n/a | **yes**: `git show HEAD:<path>`, `git log -p`, the shared object store (V1 `origin/*` branches, rolled-back candidates), `../` | by host absolute paths only (class B) | by host paths unless confined |
| **Normal coding** | none | denying bash breaks tests and the preflight smoke fingerprint | none | none | loses V1 prose, 158 workload skills, git history and the developer's own refuted candidates (developers used `git show`/`log` 69 times across the 18 developer sessions; retries inspected the named candidate) [M] | as 4b |
| **RunSpec identity** | prompt digests → `harness` setting → new RunSpec | overlay → `routing_config_digest` → `client` → RunSpec; env flags change nothing (a silent profile change) [M] | a value in the `harness` setting (`runspec.py:52-80` accepts any `{value, layer}`) [M] | `harness` | `harness` | `harness` + ATTESTED `client` |
| **Frozen item** | none (RFC §28 "prompts" input) | none | none | none | none of F1-F11; F8 acknowledgement (§6) | as 4b; conditional for S2/S3 |
| **Evidence compatibility** | attempts 3/4 verifiable | yes | yes | yes | yes (all 15 preserved candidates touch only `ledgerlock/**`, `tests/**`, mode 100644 [M]) | yes |
| **Offline testability** | presence of text only | weak | full | full | full | full for A; per-OS canary for B |
| **Workload assumptions** | none | client-version and shell specific | per-workload data; semantics are classes | none | a declared WORK set per workload | as 4b |

Only 3 + 4b closes class A, and only confinement closes class B. A filesystem policy inside the client cannot contain bash,
and a prompt cannot contain anything.

## 3. Recommended core — CTX-001 (harness-only, identical under every confinement choice)

1. **Classes, assigned by admission, never by content or name.**
   - `AUTHORITATIVE`: `{path, sha256}` entries, each equal to an admitted frozen digest (the requirements digest is already
     the RunSpec setting `requirements_sha256`, `c2_p9.py:672`). Visible; changes to them are never transplanted.
   - `WORK`: the workload's declared product and test roots and its declared build/ignore files. Visible and writable.
   - `REFERENCE` (optional, owner decision OD-1b): declared read-only source the developer may consult; never transplanted.
   - `NON_AUTHORITATIVE`: **the default** — every other tracked path. Not materialised, never transplanted.
   The rule is an allowlist and names no non-authoritative location; the string `_bmad-output` appears only in a test
   fixture that reproduces the measured defect. LedgerLock instance [M]: AUTHORITATIVE `docs/requirements.md`
   (sha256 3a6a9995…, equal to the frozen REQUIREMENTS.md); WORK `ledgerlock/**`, `tests/**`, `pyproject.toml`,
   `.gitignore`. The baseline view is exactly 3 files.
2. **Exported view.** Per developer session, a fresh single-commit repository holding only the visible classes' blobs of
   the checkout's HEAD, byte for byte; no remote, no alternates, no access to the run's object store. Optional (OD-1c): the
   previous candidate's WORK tree as a second commit, so the candidate the retry feedback names stays inspectable. The
   view's handle disposes it (INV-MUTATION-AUTHORITY: deletion only by the owning handle).
3. **Transplant guard (harness code, output side).** The kernel checkout must still be at its parent and clean; WORK
   entries are applied (blob bytes and the exec bit), all other entries are dropped and recorded per session; symlinks and
   gitlinks refuse with FAILED; then the existing `changed` check and `commit_all` run unchanged. Under no confinement
   this guard *narrows* the write-integrity hole of a host-writing developer (ignored paths and `.git` hooks remain), it
   does not close it.
4. **Identity.** The manifest and its digest go into `harness_identity()`, the RunSpec `harness` setting
   (`c2_delivery_experiment.py:199-208`: "What the developer is given, by content"); per session the harness record gets
   the view digest and the dropped paths. The client surface — global instruction file, plugins, agents, MCP server
   names and enabled flags, the Claude-compatibility surface, the skill directories, and every environment flag the
   harness sets — is digested into the ATTESTED `client` string, which is free text (`c2_delivery_experiment.py:186-191`;
   the ATTESTED tuple itself is closed, `capability.py:27-28,54-61`). Today none of it is bound [M].
5. **Audit (best effort, not a guarantee).** After each session the stream is scanned for reads of protected roots and
   framework marks; findings are recorded per session. The rule flags exactly the 3 hunting sessions of attempt 4 and none
   of the other 15 [M], but that split was fitted to known cases: recall is unmeasured, MCP calls carry no path, computed
   paths evade it. A planted-canary recall test replaces any claim of calibration. Whether a finding voids a run
   (CONTAMINATED) is an owner ruling, preregistered, not a heuristic decided after the fact.
6. **Prompts stay byte-identical to H-PROMPT-002**, so the context surface is the only variable that differs from attempt 4.

## 4. Confinement (class B) — required before any paid run

| Option | What it is | Measured or inferred limits |
|---|---|---|
| S0 detect-and-void | the core only | **not acceptable for a paid run**: the hidden stimulus already persists outside any run root — 62 copies of the S-D3-05-01-1 scenario fragment in the operator's OpenCode store (`~/.local/share/opencode/opencode.db`, mode 644) [M], the committed attempt-4 session evidence (9b919a3, `STORY-04-02.developer.3.jsonl` #171) [M], and the framework repository's own specs (`validation/qualification/p10_contracts.py`) [M]; and candidate code executed by the probe runs in the same interpreter as the probe's request (`process_effect.py:431`, the subject imported at `:523`, `:663`) [M], so read-confinement of files cannot hide the stimulus from executed candidate code |
| S1 same-user OS sandbox | deny-by-default reads and writes except the view, the toolchain (`/opt/homebrew/…`, measured in use), a private TMP and a per-run fresh OpenCode data directory; egress confined; the same launcher for developer-authored code the harness executes | macOS `sandbox-exec` present but deprecated; Windows AppContainer untested; whether the client runs under a deny-default profile is unmeasured; the credential must be placed so the developer cannot read it; needs an offline canary preflight that covers the OpenCode store, the framework checkout and closure-evidence, not only past command lists |
| S2 separate OS user | the developer runs as another user | the POSIX process range is the anchor's own session and the kernel swallows `PermissionError` on kill (`process_range.py:144-147,158-166`) [M] → a kernel change → R7 STOP, Architecture Exception, Q0-Q5 |
| S3 container / VM | the developer runs isolated | a new client identity; the container's lifetime sits outside the owned range; Windows CI gap |

Recommended path: implement and test the CTX-001 core offline; authorise an offline S1 spike on macOS and Windows; refuse
any paid run on an OS where the S1 canary is not GREEN. Separately — and whatever is chosen — the operator's OpenCode
store already holds hidden stimulus; isolating the client's data directory per run is part of S1.

## 5. Owner decisions required

- **OD-1. Is class-based non-materialisation acceptable, and not the forbidden benchmark-specific hide?** Its effect on
  LedgerLock: V1 prose, `AGENTS.md`/`CLAUDE.md`, `.claude/skills`, `evidence/` and `README.md` are absent from the view
  under an allowlist that names none of them. (a) accept as generic (recommended); (b) keep them visible (class A stays
  open); (c) visible but relocated and labelled — labelling already failed in attempt 3. **OD-1b**: a read-only REFERENCE
  class for source outside WORK (the owner's premise "may need arbitrary source code"). **OD-1c**: materialise the
  previous candidate's WORK tree in the view. Cost, stated plainly: under CTX-001, non-WORK source is invisible unless
  REFERENCE is used, and prose that lives *inside* WORK (docstrings, fixtures, earlier candidates' code) stays visible and
  unlabelled.
- **OD-2. Confinement level** (§4): S1 recommended; S0 is not a paid-run option.
- **OD-3. H-RETRY-001 search keys.** The feedback names journal seqs and the spec, probe and contract ids; the hunting
  sessions grepped the host for exactly those strings (DEVELOPER-CONFINEMENT-GAP-001 fact 6). Keep them (meaningful only
  under S1+), or strip them from the developer-visible text and keep them in the harness record. Either amends an owner
  ruling.
- **OD-4. Client-global surface.** Disable inherited MCP servers, plugins and the Claude-compatibility surface and bind
  the result (recommended), or bind only. Disabling changes tool behaviour (the plugin's rewritten form appears in 292 of the 360 attempt-4 bash calls [M]) and is therefore an experiment change, not only a context change. The flags' semantics are read from the
  client binary's strings, not verified by execution.
- **OD-5. The audit's verdict rule** (§3.5).
- **OD-6. Authorisation and order:** `c2_delivery_experiment.HISTORICAL[4]` (evidence commit 9b919a3) before any harness
  edit — a skeptic measured, in memory only, that `historical_problems` then passes for attempts 3 and 4; the K-NOWORK-001
  rehearsal re-bound (it binds `c2_p9.py`); a new attempt identity, which the current authority text forbids
  ("no attempt 5", `c2_delivery_experiment.py:70-76`).

## 6. Frozen items

- **None of F1-F11 for the core.** No aisef2 file, no journal field or event type, no ATTESTED field, no RFC text. The
  CYCLE2 R2 byte-pinned probe files are untouched. Invariant I is served by a harness mechanism, not amended.
- **F8, for the owner to acknowledge:** RFC §18 assigns "worktree, sandbox, process ranges, provider/agent sessions, tool
  grants" to the StoryScope (`RFC.md:954`) with the disposal order of §17.1 (`:927-932`). The view and any S1 sandbox are
  harness-owned resources outside that journaled stack. This extends an existing deviation — the developer's process
  range is already harness-owned and not journaled as a story resource (`c2_p9.py:461`) [M] — but it is not "NONE".
- **Conditional:** S2/S3 → F8 and the F5 reliance on the controller-owned process range → R7 STOP. Promoting context
  authority into the kernel → F1 (closed payload schemas), F10 (a new invariant-I mechanism), F9 (a new ATTESTED field).

## 7. Identity, evidence and qualification

Changed by the core: the `c2_p9.py` sha, the `harness` setting, the ATTESTED `client` string, the RunSpec template and
resolved hash → a new preregistration and attestation → a new attempt identity. Unchanged: kernel tree c2717d2e, probe
digests, semantic hashes, spec ids, plan hash, contracts, journal format, ProbeResult shape. Attempts 3 and 4 stay
verifiable from their own evidence commits (`historical_problems` reads git objects, `c2_delivery_experiment.py:957-972`).
Q0-Q3: any `tests/v2` change restarts them from Q0 (`validation/qualification/common.py:34-37`) — a restart already
pending, because the Q0-Q3 subject is pinned to c11615a (kernel 254d8f55) while HEAD carries c2717d2e. Q4/Q5: not
invalidated by this design (no rung binds the harness files); Q4-FINAL and Q5-FINAL are already stale for the current
kernel.

## 8. Offline test plan (no provider call)

(a) a fixture repository with a prose directory carrying the four-field delete, an instruction file, a skill and a
write-scope guard: the view equals exactly the visible blobs, has one commit and no remote, and `grep -r` / `git log --all
-p` inside it find none of the prose; (b) the builder on preserved `attempt-4.git@136a68d` gives exactly 3 files;
(c) transplant cases — WORK add/modify/delete/exec-bit applied, other classes dropped and recorded, symlink/gitlink
FAILED, non-pristine checkout FAILED, CRLF bytes preserved, Windows cleanup; (d) a planted-canary recall test for the
audit; (e) a scripted stand-in client on PATH through the real `implement()` that tries `ls ..`, `git log --all`,
`cat AGENTS.md` and writes one product and one non-WORK file; (f) `--check-historical` for attempts 3 and 4; (g) under
S1, the canary preflight per OS. Not demonstrable offline: that a real model then follows the requirements.

## 9. Not done, deliberately

No edit to the workload's files, the plan, the specs, the kernel or the prompts; no deletion or hiding of a named file;
no paid run; no confinement implementation.
