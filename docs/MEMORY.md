# Experimental agent long-term memory

**Default OFF. Memory is advisory context, never evidence.** Current architecture, requirements, authoritative source and gate results outrank recalled text. No session reuse, new gate, model call, embedding dependency, remote transmission, account or credential is introduced.

See [research/comparison and P0/P1/P2 plan](MEMORY-RESEARCH-PLAN.md), [ADR-007](ADR-007-scoped-advisory-memory.md), and [benchmark/security report](MEMORY-VALIDATION.md).

## Configuration

Add keys to the existing project `.ai/config.json` (do not replace your other settings):

```json
{
  "memory.enabled": true,
  "memory.provider": "local",
  "memory.fallback": "none",
  "memory.timeout_seconds": 2,
  "memory.max_chars": 1200,
  "memory.capture": false
}
```

All defaults shown except `memory.enabled`, whose default is **false**. `memory.capture=true` is currently a **no-op return** — automatic advisory capture stays disabled until an explicit verification-time authority digest is bound to records. Explicit CLI capture opts into one capture only against an authoritative artifact source; it will not invent `landed`/`failed` claims from journal events. Disabling `memory.enabled` prevents automatic reads/writes/injection and leaves rendered prompts unchanged. `status` and `providers` work while disabled. Other commands require explicit enablement. Environment overrides follow the normal `AISEF_MEMORY_ENABLED` etc. naming.

Provider options: `local`, `openviking`; fallback: `none`, `local`. OpenViking is **unavailable**, not a dummy adapter. Selecting it with no fallback yields an advisory unavailable result; explicit local fallback reports requested/actual provider and reason. No remote URL or credentials are accepted. Timeout bounds local lock waiting, **not** full disk I/O or a nonexistent remote request. Range 1–30 seconds; character budget 0–20000. Config types/ranges are checked by `Config.load`; direct programmatic `Config.overlay` follows the repository's existing non-validating behavior.

## CLI

```sh
aisef memory status --json
aisef memory providers --json
aisef memory capture --story STORY-01-01 --json
aisef memory recall --story STORY-01-06 --json
aisef memory search "bounded retries" --story STORY-01-06 --role developer --tool test --json
aisef memory show MEMORY_ID --json
aisef memory consolidate --json
aisef memory audit --json
aisef memory forget MEMORY_ID --json
```

`--project PATH` is a top-level option before `memory`. Search/recall require a real story and derive epic/path scope from the plan, not user-supplied project wildcards. All outputs are JSON (pretty by default, compact with `--json`). Failure output is deliberately generic and contains neither query nor exception payload. `show` is explicit L2 retrieval, including provenance and effective stale status, not injection. Known secrets/instruction-like content are rejected on show and recall. `forget` removes the record payload and retains an ID tombstone; repeated capture of identical content is refused. It does not erase authoritative evidence, filesystem snapshots, or backups. Audit stores IDs/selection metadata, not the query or memory body.

Normal `aisef status` adds health and resolution only when memory is enabled. Unavailability never becomes a story gate failure. Local recall/capture failures are caught at harness boundaries; disabled operation avoids touching the store.

## Schema and provider

Implementation: `aisef/memory.py`, standard library only. Store `_bmad-output/memory/store.json`:

```json
{
  "version": 1,
  "project": "sha256 of canonical project root",
  "records": {
    "content-derived-id": {
      "id": "content-derived-id",
      "project": "same project hash",
      "epic": "EPIC-01",
      "story": "*",
      "roles": ["developer"],
      "paths": ["src/workers"],
      "tools": ["*"],
      "kind": "lesson",
      "trust": "deterministic",
      "status": "active",
      "text": "Use bounded retries",
      "source": {
        "ref": "docs/conventions.md",
        "digest": "sha256 of source bytes",
        "type": "artifact",
        "at": 1789084800,
        "story": "STORY-01-01",
        "candidate": ""
      },
      "authority": {
        "docs/requirements.md": "digest or null",
        "_bmad-output/architecture.md": "digest or null",
        "_bmad-output/prd.md": "digest or null"
      },
      "contract_authority": {
        "docs/requirements.md": "64-hex capture-time digest required for active promotions"
      }
    }
  },
  "tombstones": [],
  "audit": []
}
```

`make_record` always returns `status='unverified'`. `put` rejects storing an `unverified` non-agent record and rejects storing an `active` reviewer/security record without a non-empty `contract_authority` digest. The captured `contract_authority` is preserved so that `_stale` cannot silently launder a stale authority through to recall: a record is only considered fresh against the digest that was live at capture time.
`*` is explicit applicability within **this project only**. Global sharing is not implemented. Project identity intentionally changes if the directory moves; migration is manual, never implicit. Every scope/provenance field is required. Candidate required for gate/security/reviewer/landed trust. Allowed source types are artifact/journal/evidence; lifecycle-derived records are restricted to developers. Active artifact claims must be exact source excerpts, not arbitrary generated advice. Source linkage proves where text came from, not that its claim is correct or human-authorized.

Taxonomy: decision, lesson, failure, trajectory, tool, codebase, preference, review_pattern, security_pattern, environment. Lifecycle: active, stale, superseded, revoked, unverified. Trust precedence: human > deterministic > gate > security > reviewer > landed > agent. Agent observations are unverified and never auto-promoted. Reviewer/security eligibility uses `REVIEWER_TRUST = {'gate','security','reviewer','landed','human'}` and additionally requires the record's `contract_authority` to carry a 64-hex digest; `deterministic` alone is never review-eligible, even with a contract digest. Updates only invalidate/supersede/revoke, not promote. Capture a new authoritative record for new knowledge.

`MemoryProvider` defines recall/get/put/update/forget/search/consolidate/health/stats. `LocalMemory.audit` exposes operational history. Records are deduplicated by a stable hash excluding capture time, tied to project/source digest/content/scope. `consolidate` invalidates changed source/authority references; it performs **no model summary or semantic merging**. Unknown/corrupt schemas are retained unchanged and reported unavailable. A file-size ceiling (4 MB), record ceiling (1000), per-record limits, 500-event audit tail and 6-record/1200-character default packet bound growth. Source files larger than 4 MB are refused.

Locking uses `aisef/_compat.flock_ex_nb`/`flock_un`, with portable `O_CREAT|O_RDWR[|O_NOFOLLOW]` on POSIX and `msvcrt.locking` on Windows. The lock fd is opened on `_bmad-output/memory/store.lock` with `O_NOFOLLOW` where the platform defines it; on Windows the implementation falls back to range locking. Private temporary file, fsync, atomic replacement and a project-size ceiling prevent partial JSON writes. Multi-process concurrency is exercised by the `test_process_concurrency` adversarial test (8 independent Python writers). Source/store path components reject symlinks, traversal, NUL, backslash, Windows drive prefixes, leading-hyphen parts, common credential basenames and `.env*`/`.ssh`/`.aws`/`.git`/`.pem`/`.p12`/`.pfx` extensions. There remains a hostile same-UID directory-swap race during `safe_path`’s component walk: documented as a residual risk; mitigated by journal/evidence schema requiring exit-time digests and by capturing `contract_authority` directly from `authority(root)` at `make_record` time rather than recomputing later.

## Retrieval and handoff

Eligibility first: project/epic/story/role/path/tool scope, active lifecycle, valid source digest and current authority digest. Reviewer/security additionally refuse agent/unverified memory; event-derived observations are developer-only. Lexical token overlap scores eligible records, with trust as a deterministic tiebreak component; descending score then ID stabilizes ordering. Whole-path prefixes avoid `src/a` matching `src/ab`. No embeddings or semantic model calls.

L0 metadata (ID/source type) and bounded L1 text (up to 400 chars/record) share one explicit packet; the full record is only `show`. Header and references count toward budget; records that do not fit are omitted, not silently overflowed. Negative decisions carry reasons: scope/path/no lexical match/stale/status/unsafe/budget. Query text is not persisted. Recall latency measures local selection before audit-write completion, not total CLI latency or model latency.

`phases/implement.py` attaches role-specific memory just before handoff; `harness/routing.py` appends the optional slot without modifying historical prompt templates. `SLOT_SOURCE.memory` and `EvidenceStore.handoff(..., memory=...)` carry IDs, source types, trust, role, scores, character budget, rejections, latency and provider resolution. This handoff describes what context was provided; it does **not** turn the memory assertion into evidence. The memory audit emits `memory.recall`, `memory.inject`, `memory.capture`, `memory.reject`, `memory.supersede`, `memory.consolidate`, `memory.forget`; selection records are advisory and not added as TOOL_RUN/BEHAVIOR/gate events.

## Capture

Automatic lifecycle capture (`capture_story` / `capture_advisory`) is **disabled**: it returns `{captured: [], reason: 'automatic event capture is disabled until contract authority is bound; capture only via authoritative artifacts'}` even when `memory.capture=true`. Operational capture is therefore restricted to explicit CLI or artifact paths with verified authority digests. When binding a verified authority digest per story is implemented, capture can resume with structured provenance checks: journal sources must contain a `verification.completed` entry whose `data.candidate` matches the `candidate` field and includes an explicit `passed` marker; evidence sources must contain a tool-run failure entry for the same story and candidate. No developer response, arbitrary logs, review prose, command output or entire transcript is copied.

Source digest changes can make earlier observations stale even after benign journal append. This conservative behavior sacrifices recall rather than letting out-of-date claims outrank current sources. Explicit supersession/revocation is available via provider `update`; semantic conflict resolution and a signed human promotion workflow are deferred.

## Limits and next steps

Keep OFF until real paired long-horizon trials demonstrate fewer repeated errors without stale/wrong retrieval or reviewer/gate harm. Current benchmark is scripted retrieval only. No causal efficacy, dollar savings, token savings, latency-to-completion improvement, review reduction or gate pass improvement has been established. Review/security recurrence fixtures exercise deterministic artifact excerpts, not learned cross-agent claims.

Not delivered: remote adapter, global opt-in store, cryptographic provenance authentication, semantic injection detector, signed human promotion UI, semantic consolidation, background daemon, real-agent A/B/C execution, or external independent security audit. Built-in screening is deliberately conservative and incomplete; provenance/scoping/budgets and role separation provide additional boundaries, not immunity.
