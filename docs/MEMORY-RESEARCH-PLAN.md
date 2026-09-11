# Agent long-term memory: research and implementation plan

Research inspected 2026-09-11, before design/code. Sources below were actually fetched with WebFetch; OpenViking API examples also queried through Context7 after resolving `/volcengine/openviking`. These are moving `main` README snapshots, not pinned releases or locally executed integrations. No external model, credential, account, or service was used. Versions/dependency inventories not established by README are unknown; external performance claims are not AISEF measurements.

## Comparison

| System / inspected source | Useful | Avoid for AISEF | Dependencies/runtime observed | Fit / recommendation |
|---|---|---|---|---|
| [OpenViking](https://github.com/volcengine/OpenViking), main README; Context7 main `docs/en/concepts/04-viking-uri.md`, `docs/en/api/03-filesystem.md`, `examples/basic-usage/README.md` | L0 abstract/L1 overview/L2 detail; scoped URI retrieval; observable trajectories | automatic session extraction, vector/model dependencies, implicit external transmission | Python >=3.10, server, VLM/embedding configuration; main license AGPLv3, CLI/examples separate licenses; README benchmarks mention 0.3.22, not inspected package version | Best conceptual match for tiers; do not install. Client `SyncHTTPClient(url, api_key, timeout)`, `find(query,target_uri)`, `read/abstract/overview`, HTTP DELETE `/api/v1/fs` verified in docs. Full safe put/update/consolidate and metadata fidelity contract not verified; adapter deferred, explicit unavailable status |
| [Letta](https://raw.githubusercontent.com/letta-ai/letta/main/README.md) | clear separation of historical vs active runtime | relying on retired API assumptions | README redirects to letta-code; retired V1 in archive branch | Do not integrate historical V1 |
| [letta-code](https://raw.githubusercontent.com/letta-ai/letta-code/main/README.md) | inspectable memory, git-backed MemFS, project/agent scopes, memory-quality audit | persistent identity/session reuse, self-rewriting prompts/harness, broad cross-agent message search | npm CLI/App Server; optional cloud synchronization, provider connection | Adapt inspectability, not stateful agent identity; preserve fresh sessions |
| [mem0](https://raw.githubusercontent.com/mem0ai/mem0/main/README.md) | simple memory API, user/session/agent filters, temporal retrieval | equal-weight agent assertions; ADD-only accumulation without explicit revocation; copying published managed-platform scores to OSS | Python/npm, LLM + embedding defaults, optional spaCy NLP, self-hosted stack/cloud | Interface inspiration only; no dependency. README explicitly says managed proprietary optimizations differ from OSS |
| [Graphiti](https://raw.githubusercontent.com/getzep/graphiti/main/README.md) | validity windows, source episodes, supersession without losing history | learned ontology as authority, raw episodes as injected evidence, graph operations for small local corpus | Python >=3.10, Neo4j/FalkorDB/Neptune, LLM and embeddings; Kuzu deprecated; opt-out telemetry | Adapt explicit invalidation/provenance, not graph runtime |
| [LangMem](https://raw.githubusercontent.com/langchain-ai/langmem/main/README.md) | storage-independent functional core; separate hot-path recall from background consolidation | agent-controlled writes/prompts promoted automatically | Python langmem, LangGraph integration, model provider; in-memory store volatile, production DB-backed store | Adapt provider protocol and offline consolidation, not model extraction |
| [Cognee](https://raw.githubusercontent.com/topoteretes/cognee/main/README.md) | remember/recall/forget; accepted lessons distinct from session cache; code context | automatic graph enrichment, opaque retrieval fallthrough, broad company memory by default | Python 3.10–3.14, LLM + embedding defaults, graph/vector/relational backends, optional API/UI/MCP | Explicit acceptance and lifecycle useful; not stdlib fit. README flags Postgres graph as demo/licensed production and BEAM methodology gaps |
| [LangGraph](https://raw.githubusercontent.com/langchain-ai/langgraph/main/README.md) | durable orchestration separated from memory, human intervention | replacing existing journal/FSM with second runtime, checkpoint/session memory mistaken for evidence | Python package; optional deployment/LangSmith ecosystem | Keep existing AISEF scheduler/journal; adapt conceptual separation only |

README documentation establishes concepts, not security guarantees: no system's scope filtering, deletion completeness, injection defenses, failure modes, or privacy controls were independently audited. No full dependency lockfiles or immutable upstream commits were inspected. External latency/token/success benchmarks were not reproduced and are not used to enable AISEF memory.

### Verified upstream metadata snapshot

Head-of-`main` commit dates and latest stable release tags were re-checked against the public GitHub REST API on 2026-09-11 (unauthenticated, no install, no credential use). These are observed metadata, not a contract test of any system:

| Source | Head commit | Commit date (UTC) | Latest release tag | Release date (UTC) |
|---|---|---|---|---|
| `volcengine/OpenViking` | `f55cb4170fff` | 2026-09-10T12:49:02Z | `v0.4.19` | 2026-09-08T11:59:52Z |
| `letta-ai/letta` | `5bcdd177d70f` | 2026-09-10T17:59:06Z | `0.16.8` | 2026-05-14T17:14:24Z |
| `letta-ai/letta-code` | `2d99c28a632d` | 2026-09-10T20:23:12Z | `v0.32.1` | 2026-09-10T07:44:15Z |
| `mem0ai/mem0` | `d873892dad28` | 2026-09-10T15:21:50Z | `pi-agent-v0.3.0` | 2026-09-09T14:40:27Z |
| `getzep/graphiti` | `c64e45c111fd` | 2026-09-10T20:19:37Z | `v0.30.2` | 2026-09-08T20:38:41Z |
| `langchain-ai/langmem` | `9d033b47d9ce` | 2026-09-09T06:44:42Z | none observed | — |
| `topoteretes/cognee` | `c0d18c80e24b` | 2026-09-09T16:07:02Z | `v1.5.4` | 2026-09-04T16:18:59Z |
| `langchain-ai/langgraph` | `e539ac122f41` | 2026-09-09T07:22:43Z | `sdk==0.4.4` | 2026-08-27T21:25:36Z |

These values inform future refresh decisions only; the table is informational, not an AISEF dependency declaration. The AISEF memory implementation does not call, install, or vendor any of these systems. No fresher documentation, security review, or architectural detail was discovered from this snapshot beyond what the existing comparison row text already conveys. Version pinning and contract tests remain P2 (deferred).

## Local architecture observations

`phases/implement.py::build_context` assembles current story/architecture/ledger/code context; `handoff_slots` reports provenance. `harness/routing.py::build_spec` rejects reviewer/security session resume. `harness/observe.py` owns evidence events; `control/ledger.py` derives behavior state, rather than trusting saved ledger JSON. `control/journal.py` distinguishes candidate freeze, verification and merge. Existing uncommitted repair/worktree/ownership changes were inspected and must remain intact. Memory must not introduce gate names or behavior events. Existing skills are routed advisory context, not a reason to install another orchestration framework.

## Detailed plan and acceptance

### P0 — offline safe foundation and integration

1. Versioned stdlib local JSON store outside story write scope; bounded reads, advisory errors, atomic replace under bounded interprocess lock; reject symlinks/traversal and corrupt/unknown schema without overwriting. Deterministic content IDs, dedupe, tombstones and explicit lifecycle updates.
2. Required project/epic/story/role/path/tool scope, source reference/digest/time/story/candidate provenance. Taxonomy and trust enum validation. Agent observations unverified; no automatic promotion. Current architecture/requirements/source changes invalidate conservatively.
3. Store and recall screening, no transcripts, no secret-bearing source reads, redacted audit. Explicit project opt-in only; global sharing deferred, never automatic. Reviewer/security reject agent observations and unverified entries.
4. Deterministic bounded lexical/path/role recall and L0/L1 packet, L2 CLI get. First-class optional memory handoff metadata IDs/source types/scores/budget/rejections/provider/latency. Disabled mode preserves existing prompts and sessions. Evidence/gates remain separate.
5. Deterministic lifecycle capture from journal/evidence references: landed vs failed explicitly; no raw agent log ingestion. Status and capture failures advisory.
6. CLI status/recall --story/search/show/capture --story/consolidate/audit/forget/providers, JSON. Validated explicit provider/fallback/timeout/budget. No remote provider silently enabled.
7. RED-first offline tests for storage, corruption, schema, isolation, provenance, staleness, budget, security, disabled prompts, reviewer independence, lifecycle, CLI and no gate influence.

### P1 — measurement and operational documentation

1. Reproducible long-horizon A/B/C manifest: A off, B local, C OpenViking unavailable. Deterministic scenarios story1→6 conventions, failure2→8, recurring review/security, superseded architecture, tool environment, module isolation and UI; include negatives.
2. Measure retrieval precision/recall/harm/stale/wrong retrieval and local latency only. Primary repeated-error rate, review/gate/turn/token/cost metrics null until genuine agent runs. Scripted retrieval is not causal efficacy. No fabricated ablations.
3. Research, ADR, schema/provider/security/benchmark/limitations guides and links from READMEs, SOLUTION and user guides/roadmap.
4. Full offline unittest suite, configured lint/typecheck if available, diff check, explicit review of security gaps. Nested delegation attempted but tool rejected depth >1; independent subagent review unavailable in this execution.

### P2 — explicitly deferred pending evidence/authorization

1. Pin and contract-test a real OpenViking deployment (including deletion, metadata filtering, timeout, schema and failure handling), then optional adapter with mocked protocol tests and explicit remote opt-in.
2. Authorized paired fresh-agent long-horizon experiments, randomized order/seeds and adjudicated repeated errors. Enable default only after credible efficacy without security/gate regression.
3. Human-approved cross-project/global memory and promotion workflow; semantic conflict detection; vector retrieval only if measured need justifies dependencies. No automatic prompt/skill/harness rewriting.
