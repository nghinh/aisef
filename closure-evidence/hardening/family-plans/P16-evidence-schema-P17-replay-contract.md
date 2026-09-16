# Phase 16 — evidence schema versioning / migration · Phase 17 — replay contract

## Phase 16 — evidence schema

The F1 identity model changes what an event means. `Event.identity` carries `schema_version`:

| version | events | freshness rule |
|---|---|---|
| 1 (≤ 1.7.6) | `detail.candidate` only, no identity | candidate-bound only. **Never fresh for control** under the new gate: a schema-1 record is stated (`evidence matches candidate`: `legacy evidence at <sha> — re-verify`) and the stage is re-run. No implicit upgrade by reading fields that happen to exist. |
| 2 (F1) | full identity tuple | `identity.fresh()` |

Migration: `aisef/control/evidence_schema.py::migrate(event) -> Event` maps a schema-1 event to schema-2 with
`identity = {schema_version: 1, candidate_sha: detail.candidate, story_id, migrated_from: 1}` and every other field
empty. Provenance is kept (`migrated_from`); an empty tree/config/environment digest never equals a real one, so a
migrated record can only be **shown**, never **scored**. Migration is deterministic and idempotent; it runs at read
time (`EvidenceStore.read`) and never rewrites the file.

Compatibility tests (`tests/hardening/test_evidence_schema.py`): archived 1.7.x evidence files copied from
`closure-evidence/dogfood/**/evidence/*.jsonl` (LedgerLock run 2 and the OpenCode replay) are read through the new
store: (a) every event loads, (b) none is fresh for control, (c) the gate over them says re-verify and passes nothing,
(d) a schema-2 file written by the new store round-trips, (e) a mixed file (old tail + new records) scores only the
new records. The write path stamps `schema_version = 2` on every event.

## Phase 17 — replay contract (INV-S.1)

`aisef/control/replay.py`:

- `ReplayManifest` (frozen dataclass, JSON on disk `_bmad-output/replay/<run_id>.json`): framework_version,
  client, client_version, model, route, config_digest, requirements_digest, story_contract_digests (per story),
  environment_digest (OS, python, tool image ids), sandbox_digests, baseline_identities (per story), source_run.
- `capture(project, artifact_root, config, client) -> ReplayManifest` — written at the start of every `aisef run`
  (the *source* identity), cheap: digests of files already read.
- `preflight(requested: ReplayManifest, source: ReplayManifest) -> Drift` — field-by-field comparison; material
  fields (client, client_version major, model, route, config_digest, requirements_digest, story_contract_digests,
  baseline_identities) → `STOP / DECLARE_DRIFT` with the exact differing fields; immaterial fields (framework
  patch version, host name) → recorded, not blocking.
- `aisef run --replay-of <run_id|manifest.json>` runs `preflight` **before the first agent invocation**; drift
  stops the run with a typed `REPLAY_CONDITION_DRIFT` record unless `--accept-drift <field,...>` names each
  differing field (the owner's explicit approval, recorded in the manifest).

Deterministic tests (`tests/hardening/test_replay_contract.py`): the Claude-vs-OpenCode mistake — a source manifest
with `client=opencode` and a requested run with `client=claude` — is stopped before any client call (synthetic
client's `calls == []`); a same-identity replay proceeds; an accepted drift is recorded with the accepting flag;
a changed story contract digest is material; a framework patch bump alone is not. FM-X-01 turns GREEN.

Scope guard: no replay product surface beyond capture + preflight + the one flag.
