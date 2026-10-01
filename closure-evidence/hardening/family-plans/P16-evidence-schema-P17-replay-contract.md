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

## Closure record (2026-09-17, branch hardening/systematic-v1)

**Phase 16.** The migration the plan names as `evidence_schema.py::migrate` had already been realised by F1 inside
`control/identity.py::EvidenceIdentity.of` (schema-1 → identity with `schema_version = 1` and nothing but the
candidate; deterministic, idempotent, at read time, the file never rewritten) — no second module was written.
What Phase 16 added is the proof over the archived corpus and one kernel fix the proof exposed:
`tests/hardening/test_evidence_schema.py` reads the three LedgerLock 1.7.4 replay files
(`closure-evidence/dogfood/ledgerlock-run2/**/*.evidence.jsonl`, 249 / 1710 / 2207 events) through the new store:
every event loads as schema 1 and the record stays schema 1; no archived record is fresh for a schema-2 identity;
the CURRENT gate, deciding on such an identity with the archived run's own inputs, passes nothing and scores no
record-scored check from a legacy record; a schema-2 record round-trips; a mixed file scores only the new record.
Measured before the fix: `test`, `lint` and `security` scored PASSED from UNBOUND 1.7.4 records (in-session tool
runs with no candidate) because the story path kept unbound observations for scoring — the gate as a whole was
already refused by `evidence matches candidate` (UNRUNNABLE, "schema 1 … re-verify"), so control was safe, but a
migrated record was being SCORED, not shown. Fix: on the story path an unbound tool run is dropped before scoring
(`gate.evaluate`), EXCEPT a record that is unbound by construction rather than by age — `test:baseline`, captured at
the epoch's root before any candidate exists and compared against the candidate, never scored as it
(`gate.UNBOUND_BY_DESIGN`; the first cut dropped it too and the full suite named nine baseline tests); the legacy
candidate-only decider (`aisef gate`, `aisef replay`) is unchanged by design.
Constraining suites (gate, gate qualification, replay re-score, closure, fault matrix, freshness, judgment,
judge-only): 412 passed, unchanged.

**Phase 17.** `aisef/control/replay_manifest.py` (re-exported from `control/replay.py`, whose gate re-scoring keeps
its name): `ReplayManifest` (framework_version, client, client_version, model, route, config_digest,
requirements_digest, story_contract_digests, environment_digest, sandbox_digests, baseline_identities, source_run,
host, accepted_drift), `capture` (written at the start of EVERY `aisef run` to `_bmad-output/replay/<run_id>.json`;
the client version is probed only from a real adapter's binary, never inferred from a display name), `preflight`
(material: client, client major version, model, route, config, requirements, story contracts, environment, sandbox
images, baseline identities; immaterial: host and a framework PATCH bump — a minor or major framework change is
material, the rules differ), `record` (the typed `REPLAY_CONDITION_DRIFT` / `REPLAY_CONDITIONS_MATCH` record,
written whether or not the run stops). `aisef run --replay-of <run|manifest> [--accept-drift f,g]` runs the
preflight after the adapter exists and before any git or agent work. Tests: `test_replay_contract.py` — the
Claude-for-OpenCode mistake is material and stops the CLI with the synthetic client's `calls == []` and no sprint;
same identity proceeds; accepted drift proceeds and stays on the record; a changed story contract is material; a
framework patch is immaterial, a minor bump is not; a client patch is immaterial, a major is not; a field the
source never recorded is not compared. FM-X-01 and FM-C-09 turned GREEN; INV-S.1 PROVEN — registry 50 PROVEN / 0 PARTIAL / 0 MISSING of 50.
Scope guard held: capture, preflight, record and the one flag; no other replay surface.

CI on 9e8fc77 (run of 2026-09-16, PR #6): 7/7 green — Linux 3.11–3.14, Windows 3.11, lint, wheel. Windows is green with the unified snapshot walker, the POSIX-only zombie collection and positive session ownership all in place: this family is re-qualified on both operating systems.
