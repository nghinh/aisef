# AISEF v2.3 — THREAT MODEL (W0)

**Baseline:** HEAD `1bf5dd2f`, branch `release/v2.3-big`. Extends, never weakens: `docs/v2/V2-STABLE-RELEASE-CHARTER.md:84-104`
(the 2.0 threat model, `:97-103`), README "What 2.2 claims" (`README.md:171-222`), `docs/v2.1/ANCHOR-THREAT-MODEL.md`, RFC §4/§24/§25/§34.

> **DISCLOSURE.** This file names unpatched, reproducible bypasses (the GF-QUAL-2 forgery, GF-AUTH-1/2, GF-LIN-1, CA#9/#20).
> Owner ruling §D applies: **no push to a public remote before a disclosure review.** Keep it on the isolated branch.

**Provenance key.** `✓` = re-read at `1bf5dd2f` while writing this file. `CA#n` = defect *n* of `CODE-AUDIT.md` (45-row table).
`GF-*` = a gap-fill lane finding (read-only probe at `1bf5dd2f`). Each is now a CODE-AUDIT defect (#46–#104, adjudicated at the W0 closure); the GF→CA# map is in §8, and the IDs
are kept only as cross-references (index in §8). Other `path:line` citations come from `CODE-AUDIT.md` or the gap-fill outputs, as marked.

---

## 1. Assets

| # | Asset | Why it matters | Where it lives |
|---|---|---|---|
| AS1 | **Product truth**: frozen requirements, approved `BehaviorContract`s, `ContractApproval`s, the plan | Invariant I: only this defines correct | bundle (`aisef-v2-project/1`), `product/approval.py`, `plan/obligation.py` |
| AS2 | **Sealed oracle**: stimulus/observable/expectation | Proof independence (Invariant III). **Hiddenness is not a claim** (V21-08, §14) | bundle, contracts, probe scratch |
| AS3 | **Verdict channel**: probe protocol, `ProbeRecord`, `bound_result` | Candidate code must not control it (2.0 charter `:101`) | `probe/protocol.py`, `probe/cli_invocation.py` |
| AS4 | **Run evidence**: journal chain, `RUN.started.json`, `RUN.json`, session streams, preflight ledger, `EVIDENCE.json`, anchor | Re-derivable verdict, `--verify` | `<out>/` (operator-writable) |
| AS5 | **Spend accounting**: ledger, streams, lineage, budgets | Unknown spend must never read as 0 (V21-77/78) | `<out>/`, `app/client.py` Budget, `app/lineage.py` |
| AS6 | **Provider credential** + `client_env` secrets | Exfiltration = money + account | operator env, client `opencode.json` |
| AS7 | **Host integrity**: operator FS, processes, network | Destructive authority (INV-MUTATION-AUTHORITY) | host |
| AS8 | **Kernel identity**: `kernel_digest`, invariant digests, `engine_digest`, `EXECUTION_DIGEST` | Comparability (Invariant V), reuse keys | `app/run.py:93-99`, `plan/static_admission.py:32-40` |
| AS9 | **Qualification evidence**: mutation records, calibrations, currency DAG, owner rulings, `RELEASE-DECISIONS.json` | Release gate; F5 reuse | `validation/`, `closure-evidence/` |
| AS10 | **Historical evidence** V1/V2.0/2.1/2.2 + tag `v2.2.0` + PyPI 2.2.0 bytes | Immutable (charter §4) | `closure-evidence/**`, git tag, PyPI |
| AS11 | **Delivered `main`** | Only a journaled COMMIT may land | run clone `main` |
| AS12 | **W0 audit findings** (this file, `CODE-AUDIT.md`) | Unpatched bypass detail | `docs/v2.3/` |

## 2. Actors and trust levels

| Actor | Trust | Basis / runs as |
|---|---|---|
| **Owner** (`human:owner`) | TRUSTED. Sole authority for approvals, release, spend and privileged ops | `approval.py` `human:<name>` (CA map product/probe); ledger `RELEASE-DECISIONS.json` |
| **Operator** | TRUSTED. Holds settings, key, run dir and anchor store | 2.0 charter `:99`; README `:177` ✓ |
| **Developer agent** (LLM via OpenCode) | UNTRUSTED: faulty, opportunistic, prompt-injectable | Runs as the **operator's OS user**; confinement is opt-in, Linux-only (`settings.py:110` ✓, `confine.py:181-182` ✓) |
| **Reviewer / finder** (model or OCR) | UNTRUSTED data; never sole blocking authority | `orchestrate/adapters.py:64-65` (D-002, RFC §25) |
| **Candidate code** (developer-authored product + tests) | UNTRUSTED | Executed **unconfined** by the kernel at test/probe time (`confine.py:29-31` ✓) |
| **Probe subject** | UNTRUSTED. Its channel is authenticated; its **answers are not** (PM-5) | Separate process; HMAC protocol (`cli_invocation.py:1072-1076` ✓) |
| **Provider / router** | UNTRUSTED for identity (may alias or re-route); trusted only to bill | preflight attestation (CA map client/preflight) |
| **Mutants / mutation worker / test output** | UNTRUSTED: may only *report* pids/paths | INV-MUTATION-AUTHORITY; `validation/v2/cleanup_authority.py` |
| **Branch committer / Claude Code lanes** | TRUSTED-BUT-FALLIBLE: can write records and ledgers | the ledger is not signed (CA map qualification/release) |
| **CI (GitHub Actions)** | SEMI-TRUSTED executor of repo code | PR jobs get no secrets; only `conformance.yml:17` ✓ uses `ANTHROPIC_API_KEY` |
| **Release publisher** (`release.yml` `publish` + PyPI OIDC) | TRUSTED pipeline; **the human gate is missing** | `release.yml:73-97` ✓, `RELEASE-GOVERNANCE-FINDING.md:9-14` ✓ |
| **External evaluators (B2)** | TRUSTED for labels, independent of the developer | W6 |
| **Other OS users** | Out of scope except where 0700/0600 modes bind them | `diagnostics.py:41-42` ✓ |

## 3. Trust boundaries, threats, mitigations, gaps

Format per boundary: STRIDE letter · threat · **current control** (path:line) · **gap** (or NOT ENFORCED) · **closing v2.3 item**.

### TB1 — Owner → product truth (approval, plan)
| T | Threat | Control | Gap | Closes |
|---|---|---|---|---|
| S/E | A model or tool mints an approval | `human:<name>` + hash binding (`approval.py:61,73`, CA map); placeholder refused (`bundle_cli.py:656`); migrate never mints (`bundle_cli.py:412`) | none found | — (B4: `draft` must sign nothing) |
| T | The plan's obligation set or roles are changed after approval | `plan_hash` is a self-digest (`obligation.py:99-102`, GF) | **NOT ENFORCED.** The plan is not approval-bound: `ContractApproval` binds requirement+contract only (`test_static_admission.py:58-59`, GF) | **B4/B6b** (gated by the STOP in §7) |
| T | A plan omits every obligation of an approved contract, or binds one criterion twice in a story | static admission checks 1/3/8 | **NOT ENFORCED** (GF-PLAN-5, GF-PLAN-1) | B4/B6b, W4 L4-PARALLEL (CA#67/#71; #71 owner decision in DAG §5a) (was "W1 adjudication") |
| R | The admission decision is not in the chained record | holds by control flow only (`run.py:595-598` ✓) | `plan/static-admitted` is never emitted (GF-PLAN-6); the result is not bound to `plan_hash` (GF-PLAN-4) | E1/E6 (journal-backed gates) |

### TB2 — Developer agent ↔ oracle and harness (read side)
| T | Threat | Control | Gap | Closes |
|---|---|---|---|---|
| I | The developer reads the stimulus or bundle from the served tree | public `FACT_FIELDS` split (`bundle.py:38,211-213`, CA map); G1 tree scan (`run.py:590-594` ✓) + per-session prompt/env scan (`client.py:324-328`) | the scan **excludes `.git`** while the sessions bind the full object store RO (CA#19; `tripwire.py:116` ✓, `confine.py:196` ✓); files over 2 MiB, unreadable or non-UTF-8 are skipped silently but counted (GF-SEC-1; `tripwire.py:118-124` ✓); composite needles depend on format (GF-SEC-1b) | **G1 hardening** (W3) + D1 |
| I | The developer reads the run dir (journal, probe scratch, PM-8 observations, review findings) | none by default; bwrap hides it only when confined | **NOT ENFORCED** without confinement (`tripwire.py:26-30` ✓ STATEMENT; `diagnostics.py:41-47` ✓ "same-user, not enforced"; GF-SEC-3); measured in attempt 4 (V21-02) | **D1, D2, V21-02** |
| I | Retry feedback leaks the oracle | prompts are built from facts + typed codes; REVIEW rows only when `passed` is False (`feedback.py:86-87`) | the review anchor reasons carry sealed observables into journal/RUN.json; they stay out of the prompt only through an unrelated filter (GF-SEC-4); retry evidence can cite an older attempt's proof (GF-SEC-1c) | **G4** (evidence-as-files, stimulus-free) |
| D | An unbounded `retry_feedback` breaks the Windows argv limit | `context_pack` is bounded (`feedback.py:108-109` ✓) | `retry_feedback` is unbounded (GF-SEC-2) | **G4** |

### TB3 — Developer session → host, network, secrets
| T | Threat | Control | Gap | Closes |
|---|---|---|---|---|
| I | A session tool reads the provider key | env whitelist (`client.py:233-235` ✓); `redact()` after the session (`client.py:283` ✓) | **NOT ENFORCED** live: `XDG_CONFIG_HOME` (the key-bearing config) is kept (`client.py:231-234` ✓); the key is in `client_env`/secrets (`run.py:653` ✓); bwrap binds the config dir RO (`confine.py:195-196` ✓) (CA#9) | **D3** (loopback key broker; measure asserts no key in env) |
| I/E | The key or artifacts are exfiltrated to any host | none | **NOT ENFORCED**: `--share-net` (`confine.py:18-20,164` ✓) (CA#20) | **D3** (egress allowlist to the attested endpoint) |
| T/E | Writes outside the worktree | Linux bwrap (opt-in) + `measure()` refuses on deviation (`confine.py:22-29` ✓); G2 fence declared to the client only, "NOT measured" (`client.py:345-346` ✓) | default unconfined; no macOS/Windows backend (CA#43; `confine.py:181-182` ✓) | **D1, D2** |
| T | Developer repoints `.git` or plants git config | `workspace.git()` isolation, gitfile pinned (B4; CA map orchestrate) | none found | — |

### TB4 — Candidate code (product + developer tests) → kernel quality gate and host
| T | Threat | Control | Gap | Closes |
|---|---|---|---|---|
| E | Candidate code runs with operator privilege and network at test/probe time | owned `ProcessRange` (P4); stdlib runner | **NOT ENFORCED**: unconfined (`confine.py:29-31` ✓; CA#21) | **D1** |
| S/T | **A test forges the adequacy evidence** (the result set is produced inside the subject's own process) | none. The docstring calls it "harness-produced" (`test_execution.py:21-23` ✓), but the file is written by the same interpreter that imports the untrusted tests (`_UNITTEST_RUNNER` ✓) | **NOT ENFORCED** (GF-QUAL-2 = CA#80, P2 after adversarial verification). Blocking, because the live policy is `TestsPolicy(True)` (`run.py:672` ✓) | CA#80, W3 L3-SANDBOX: an authenticated result channel out of the subject's process (ARCHITECTURE.md:332); D1 alone does not fix it (same process); S4 STOP only if demotion were the sole remedy |
| T | Coverage is blind to import-time and subprocess execution, yet reports FULL | — | IRRELEVANT is read where UNMEASURABLE holds (GF-QUAL-1 = CA#79, P2 after adversarial verification; RFC §24 "no silent degrade") | W3 L3-SANDBOX (CA#79) |
| T | Vacuity attribution: the neutralised run differs from the candidate run in more than the reversal | — | a test can detect the counterfactual tree (GF-QUAL-4) | NEW |
| D | Subject-shaped JSON raises `InvariantError` (a `BaseException`, `errors.py:8` ✓) and aborts the **whole run** | `except` at `run.py:691` catches `Exception` only | subject-triggerable run abort (GF-QUAL-3); the same family as CA#2 | **E5** (W1b) contains `Exception` faults only; `InvariantError` stays on the interrupt path by design (W1-DESIGN §4.8(3)) — the typed parse that stops subject JSON raising `InvariantError` is CA#81/GF-QUAL-3 (W3) |
| E | An import failure typed INTEGRATION never blocks; a deliberate UNRUNNABLE retries as ENVIRONMENT | — | the story merges with 0 story tests run (GF-QUAL-5, GF-QUAL-8) | NEW |

### TB5 — Probe subject → verdict channel
| T | Threat | Control | Gap | Closes |
|---|---|---|---|---|
| S/T | The subject forges a protocol line | per-evaluation HMAC key, cleared before the subject exists; only MAC'd lines count (`cli_invocation.py:1072-1076` ✓) | none found | — (holds since 2.0) |
| T | A record answers another spec, revision or enforcement | `bound_result` PROBE-BIND (`protocol.py:223-235` ✓); `PARTIAL` is not comparable with `FULL` (§24) | none found | — |
| T | `.pth` planted in the probe venv | `-I -S` controllers (V21-28 closed at the mechanism level, `README.md:200-204` ✓) | not measured end-to-end in a live run | D1 |
| S | **The subject answers for itself** (exit code, return value, reads `sys.flags.isolated`) → SATISFIED | none. The limit is documented (`ANCHOR-THREAT-MODEL.md:48-62` ✓; V21-26) | **NOT ENFORCED** (PM-5, measured repro-5) | **E3** (OS-observed exit/signal tier), **for exit/signal observables only**. Return values stay subject-claimed |
| D | False REFUTED (controller is a permanent range member) | fail-closed direction | CA#16 | W2 L2-PROBE-OS (CA#16) |

### TB6 — Reviewer / finder → control
| T | Threat | Control | Gap | Closes |
|---|---|---|---|---|
| E | A model finding blocks alone, or prose becomes control | `Finding.blocks` = blocking ∧ corroborated (`orchestrate/adapters.py:64-65`); invariant VII | none found | — |
| T | The reviewer mutates the candidate | `tree_of`/`_unchanged` re-hash (`app/adapters.py:146,151,171,330-338`); checkout `--force` + `clean -ffdxq` (`workspace.py:149-153`) | `ReadOnlyScope` is not confinement: the root stays writable, chmod is reversible, `read()` accepts `../` or an absolute path (`orchestrate/adapters.py:76-84` ✓; GF-SEC-5) | D1 (reviewer under the same wrapper) |
| S | Reviewer binary identity | sha256 pin, re-checked at use (D4) | self-declared version, not build provenance (CA#25) | **G3**, C7 |
| D | False blocking on a reviewer-chosen `within_s` | — | CA#4 | B5 |

### TB7 — Provider / router → model identity and spend
| T | Threat | Control | Gap | Closes |
|---|---|---|---|---|
| S | Bait-and-switch after preflight | one-shot attestation: listing + per-probe `served_model` + single fingerprint; no-redirect opener (`preflight.py:25-34,124-141`, CA map) | **NOT ENFORCED** during paid turns (CA#8) | **C7** |
| S | The endpoint routing differs from the attested endpoint | endpoint is https or http to loopback (`settings.py:68-76` ✓) | the endpoint comes from the client's own `opencode.json` (V21-29); string loopback trusts `/etc/hosts` (accepted, `settings.py:73-74` ✓) | **V21-29**, C8, D3 |
| D/R | Overspend | 4-counter budget + `max_cost`, fail-closed (C2) | in-flight request under SIGKILL is outside the envelope (A-03, `README.md:205-208` ✓) | **E2** |

### TB8 — Operator-writable run directory → verifier (`--verify`, `bundle continue`)
| T | Threat | Control | Gap | Closes |
|---|---|---|---|---|
| T | The record raises a verdict | nothing in the record can RAISE a verdict (`verify.py:5-13` ✓); `_projection_refusal` | none found | — |
| T/R | **Consistent rewrite of the whole directory** | manifest + `--expect-anchor` from an off-box value (`verify.py:167-172` ✓); anchor file O_EXCL/O_NOFOLLOW/0444 | chain is unkeyed sha256 (`event.py:12-15` ✓); without the anchor it proves **consistency only** (CA#10, CA#22) | **A2** (QĐ#1 decided: per-run ephemeral keypair, public half escrowed off-box; `--expect-pubkey`) |
| T | Spend streams tampered or truncated | re-derived from streams + ledger | money is not chained (CA#12) | **E4** |
| T | Journal valid under writer rules but invalid under projection rules | writer-validator at reconstruct | lifecycle encoded twice (CA#11) | **E6**, E1 |
| T | Continue without an anchor | manifest compared only with `--expect-anchor` | V21-54 (owner decision open) | V21-54 |
| R | A named run whose directory is emptied counts as zero spend; the lineage walk stops there | missing directory → UNREAD (V21-77) | GF-LIN-2 | **E2/G6** (before resume) |

### TB9 — Concurrent claimants → continuation authority (lineage)
| T | Threat | Control | Gap | Closes |
|---|---|---|---|---|
| S | A **live** claim is judged "provably gone" | O_EXCL claim; `_gone` returns None on unknown (`lineage.py:278-287` ✓) | `ps -o lstart=` text depends on the caller's TZ/locale (`lineage.py:264` ✓) → `now != started` → supersede by "evidence" (GF-LIN-1, P1); the superseded child is not fenced before `run.begin()` (`run.py:549`→`:630` ✓) | **NEW, before G6/C5** (sibling of V21-41) |
| T | A superseded child accepted as `--parent` forks the lineage | claim checks only claims *on* the parent | GF-LIN-3 | G6 |
| D | `write`/`fsync` failure after O_EXCL leaves a raw `OSError` and a 0-byte claim | — | GF-LIN-4 | G6 |

### TB10 — Implementation, mutant or test output → host destructive authority (INV-MUTATION-AUTHORITY)
| T | Threat | Control | Gap | Closes |
|---|---|---|---|---|
| E | A mutant-reported pid gets a real signal | `cleanup_authority` re-proves ancestry, birth and group from the host table; POSIX fails closed | Windows reader returns `{}` on error (`cleanup_authority.py:209-210` ✓) and the consumer reads that as "all gone" (GF-AUTH-6); `owned()` has no child≥parent birth check (GF-AUTH-9) | NEW (W1/W3; Windows parity) |
| E | A new kill/rmtree site lands unledgered | `destructive_authority` AST checker + ledger | **NOT ARMED in branch/PR CI**: the live-tree check and all of `CheckerCalibration` are `@sealing` (`sealing_gate.py:28-32` ✓), and the job runs only on master/tags (`tests.yml:76` ✓) (GF-AUTH-1, P1). This breaks the gate's own rule (`sealing_gate.py:10-11` ✓). Other gaps: exists-semantics (GF-AUTH-2, P1); alias/shell discovery fails open (GF-AUTH-3); scope omits `validation/v21`, `validation/qualification` (`destructive_authority.py:33` ✓; GF-AUTH-4); signal-0 accepted without a POSIX guard (GF-AUTH-5) | **F2** (test markers) + NEW. W1 owns `sealing_gate` |
| E | Mutation worker runs the real client | env guard: PATH without opencode + scratch XDG (CLAUDE.md) | procedural only | W1 F5 runner |

### TB11 — Tests and agents → frozen historical evidence
| T | Threat | Control | Gap | Closes |
|---|---|---|---|---|
| T | A test or agent rewrites released records | V1 only: preventive hook + detective CI step (`tests.yml:61-64` ✓) | `closure-evidence/v2/**`, including the v2.0/2.1/2.2 releases, is **excluded** (`v1_evidence_guard.py:39-41` ✓; GF-AUTH-7); the post-suite check is manual (CLAUDE.md) | **W1** (F5 tamper negatives) + COMPATIBILITY-MATRIX freeze + guard extension |

### TB12 — Qualification evidence → release gate (currency, reuse)
| T | Threat | Control | Gap | Closes |
|---|---|---|---|---|
| S/E | Unauthorized reuse ("owner ruling" by file presence) | both source endpoints pinned by digest | ruling only `is_file()` (`mutation.py:1642` ✓; CA#14); 0 tests (CA#15) | **F5** |
| T | A stale record passes as current; reuse presented as measurement | live-tree + git re-derivation; exact `version_forward` match | version-derived pointers orphan on a bump (EVID-COUPLING-01, CA#3); `release_calibration --write` rewrites `calibrations.py` → new kernel digest (RISK-REGISTER) | **F5/EVID-COUPLING-01** |
| T | A reuse key omits behaviour-changing dependencies | — | `engine_digest` hashes 2 files only (GF-PLAN-3). **F5 must not use it as an impact key** | **F5** (transitive closure input) |
| T | Calibration drift goes undetected | fast one-direction test | rows bind no fixture sha; `--check` is not wired into CI (GF-SEC-7) | F5/F2 |
| R | History freeze is over uncommitted entries | — | CA#17 | W1 L1-QUAL (CA#17, append-only correction) |

### TB13 — Branch committer → owner authority ledger
| T | Threat | Control | Gap | Closes |
|---|---|---|---|---|
| S | Forged `approver: "human:owner"` entry or `V<ver>-STATUS.json` | none cryptographic: the branch is assumed owner-controlled (CA map qualification/release) | a revocation must reuse the `PRODUCTION_PUBLISH` key (`v2_release_gate.py:61`) | **REL-GOV-01** (the human gate is the control; the ledger stays a record) |

### TB14 — Tag → production PyPI
| T | Threat | Control | Gap | Closes |
|---|---|---|---|---|
| E | Unattended production publish | stable-tag regex → tests + staging + v2-gate; OIDC, no token (`release.yml:78` ✓) | **NOT ENFORCED**: `pypi` env `protection_rules: []` (`RELEASE-GOVERNANCE-FINDING.md:9-14` ✓; CA#1) | **REL-GOV-01** (owner adds a reviewer; verify `status: waiting`) |
| T | Published bytes ≠ frozen RC | `release_rc.py --verify-dist` (`release.yml:95-96` ✓), `sha256sum -c` (`:89` ✓) | sdist depends on host file modes (BUILD-REPRO-01, CA#7) | **BUILD-REPRO-01** (normalize modes; contract test) |

### TB15 — CI secrets and spend
| T | Threat | Control | Gap | Closes |
|---|---|---|---|---|
| I | Fork PR exfiltrates a secret | no secret on `pull_request` | none found | — |
| E | Unmetered paid spend | — | weekly cron with `ANTHROPIC_API_KEY` (`conformance.yml:9-17` ✓; CA#29), outside charter §4 economics | **Owner STOP (§7)** |

### TB16 — Kernel fault containment and identity
| T | Threat | Control | Gap | Closes |
|---|---|---|---|---|
| D | One story fault escalates to the run: no dispose, no `story/end`, shutdown refused | per-stage typed catches | CA#2 (P1); RUN.json write can be skipped (CA#18) | **E5** (mandatory, early), E7 |
| T | Same tree, different `kernel_digest` across OSes | content LF-normalized | path sort is platform-flavoured (CA#41, latent) | W1/W2 (versioned digest; never rebind 2.2 records) |

## 4. Explicit non-goals (v2.3 does NOT defend against)

1. **A malicious operator, or the machine owner attacking the framework** (`V2-STABLE-RELEASE-CHARTER.md:93-94` ✓; plan §4 Trust).
2. **A signer whose key lies in the adversary's write domain** (directive W2). A2 proves only the declared signer's custody.
3. **Hostile multi-tenant isolation**, and same-user process secrecy (KERN_PROCARGS2, V21-05).
4. **Live `aisef run` on Windows** unless a native end-to-end canary proves it (`RELEASE-CHARTER.md:48-49` ✓). Windows unit CI is not that proof.
5. **A contract faithful to a wrong requirement** (RFC §34.1); provider changes nothing can observe (§34.3); journal + sentinel + FS failing together (§34.4); preventing orphans after a hard kill (§34.5, detection only).
6. **The truth of a subject's self-report** beyond the E3 OS-observed tier (PM-5).
7. **Retroactive authenticity of 2.2 runs.** They verify as consistency-only, forever (charter §4).
8. **Cryptographic authentication of owner ledger entries.** The control is the REL-GOV-01 human gate.
9. **Build provenance** of the OpenCode client or OCR binary beyond a sha256 pin or source-commit pin (D4/G3).
10. **GitHub/PyPI platform compromise.** Deflate identity across arbitrary zlib builds.

## 5. Claims v2.3 MAY make (each only once its gate passes, each naming its weakest path, RFC §24)

| # | Claim | Gate |
|---|---|---|
| M1 | Candidate code cannot forge a probe protocol line or rebind a probe record (holds since 2.0/2.1) | existing tests + W1 negatives |
| M2 | `--verify --expect-pubkey` REFUTES any consistent rewrite of the run dir **when the public half came from a store outside the adversary's write domain** | A2 + adversarial-rewrite negative |
| M3 | No in-flight provider request is accounted as 0: it reads RESERVED/UNKNOWN; stream segments are chained | E2, E4 + SIGKILL-window test |
| M4 | Developer session, developer tests and probe subject run confined, with a declared R/W/network policy, on **Linux (bwrap)** and **macOS (Seatbelt, best-effort)**, with measured escape canaries; no raw provider key in session env, config, logs or prompts; egress limited to the attested endpoint | D1, D2, D3 canaries |
| M5 | The served model is re-attested across paid sessions; drift is detected **within observable fingerprints** | C7 |
| M6 | Reused qualification evidence is labelled `VERIFIED_REUSE` with a bound equivalence proof and never shown as `MEASURED`; stale, tampered, platform-mismatched or unauthorized evidence → `INVALIDATED`/`UNRESOLVED` | F5 negative tests |
| M7 | A production publish needs an **observed** human approval | REL-GOV-01 verified (`status: waiting`) |
| M8 | Wheel and sdist are byte-identical for the **tested pinned toolchains** | BUILD-REPRO-01 contract test |
| M9 | Historical 2.2 runs still verify (consistency-only) | COMPATIBILITY-MATRIX read test |

## 6. Claims v2.3 may NOT make (no overclaim)

- Any protection against a malicious operator, owner or same-host OS owner; "isolation" on Windows; a live Windows run.
- That test-adequacy evidence is harness-produced or unforgeable (GF-QUAL-2) or that coverage is FULL (GF-QUAL-1), until they are fixed.
- That `--verify` without an off-box `--expect-anchor`/`--expect-pubkey` proves authenticity; that a valid signature proves the run happened as journaled (`ANCHOR-THREAT-MODEL.md:8-10` ✓).
- That a probe PASS proves the product works for a user (PM-5), except observables under the E3 tier.
- That a plan (above all a B4 model-drafted plan) is owner-approved, while the plan is not approval-bound.
- Stimulus hiddenness as a guarantee, without measured D1/D2 confinement.
- That INV-MUTATION-AUTHORITY's static check is armed in branch CI, or that v2.x records are mechanically immutable, until GF-AUTH-1 and GF-AUTH-7 are closed.
- That a ledger entry is an owner approval or an interactive gate.
- `plan_quality_verdict` (always `NOT_CLAIMED`, `run.py:713`) or any generalization claim. Cohort lifecycle state is caller-held and unbound (GF-COH-1/2).
- Egress confinement before D3; cross-zlib reproducibility.

## 7. Threat-model owner STOPs (only those that change a guarantee, spend or publication)

| # | Decision | Why it is a STOP | Wave |
|---|---|---|---|
| S1 | **REL-GOV-01**: add a Required reviewer to the `pypi` env | publication control. The agent does not change repo settings | before any v2.3 tag |
| S2 | **`conformance.yml` paid cron** (CA#29): keep, cap or disable | spending authority; outside charter §4 | W1 (now) |
| S3 | **Plan approval binding** for B4: bind the plan into the approval, or keep plans unapproved | changes the approval/security guarantee and maybe bundle format `/1` (immutable compat) | before W5 B4 |
| S4 | **Test-adequacy remedy** (GF-QUAL-2) if the only feasible fix demotes adequacy from blocking to informational | weakens a shipped gate (`TestsPolicy(True)`) | W3 D1 freeze, L3-SANDBOX (GF-QUAL-2 = CA#80) (STOP only on demotion) |

Not STOPs (already decided, do not re-ask): A2 key model (QĐ#1 decided), D1+D2+D3 scope (QĐ#3 decided), A-03 envelope (owner 2026-10-31),
lineage rules V21-77/78/79/80 (owner 2026-10-18).

## 8. Gap-fill index (now CODE-AUDIT #46–#104; all five gap-fill P1 candidates were adversarially verified and downgraded to P2)

Matched by path:line and summary. "Sev TM→CA" shows where THREAT-MODEL's severity is now stale.

| GF | CA# | Sev TM→CA | CA wave / lane |
|---|---|---|---|
| GF-PLAN-1 | #67 | P2 | W4 L4-PARALLEL |
| GF-PLAN-2 | #68 | P2→**P3** | W4 L4-PARALLEL |
| GF-PLAN-3 | #69 | P2 | W4 L4-PARALLEL |
| GF-PLAN-4 | #70 | P2 | W4 L4-PARALLEL |
| GF-PLAN-5 | #71 | P2 | W4 L4-PARALLEL |
| GF-PLAN-6 | #72 | P3 | W2 L2-JOURNAL |
| GF-QUAL-1 | #79 | **P1→P2** | W3 L3-SANDBOX |
| GF-QUAL-2 | #80 | **P1→P2** | W3 L3-SANDBOX |
| GF-QUAL-3 | #81 | P2 | W3 L3-SANDBOX |
| GF-QUAL-4 | #82 | P2 | W3 →L3-SANDBOX |
| GF-QUAL-5 | #83 | P2 | W3 L3-SANDBOX |
| GF-QUAL-6 | #84 (relevance.py:101-113, vacuity.py:103-125) | P2 | W3 →L3-SANDBOX |
| GF-QUAL-7 | #85 (vacuity.py:204,208) | P2 | W3 →L3-SANDBOX |
| GF-QUAL-8 | #90 | P3 | W3 L3-SANDBOX |
| GF-AUTH-1 | #46 | **P1→P2** | W1 L1-F5 |
| GF-AUTH-2 | #47 | **P1→P2** | W1 L1-AUTHCHK |
| GF-AUTH-3 | #48 (:36-238) | P2 | W1 L1-AUTHCHK |
| GF-AUTH-4 | #49 (:33) | P2 | W1 L1-AUTHCHK |
| GF-AUTH-5 | #50 (:64,427-430) | P2 | W1 L1-AUTHCHK |
| GF-AUTH-6 | #51 | P2 | W1 L1-AUTHCHK |
| GF-AUTH-7 | #52 | P2 | W1 L1-CIGOV |
| GF-AUTH-8 | #53 | P2 | W1 L1-AUTHCHK |
| GF-AUTH-9 | #58 | P3 | W1 L1-AUTHCHK |
| GF-AUTH-10 | #57 | P3 | W1 L1-AUTHCHK |
| GF-LIN-1 | #60 | **P1→P2** | W3 L3-PLATFORM |
| GF-LIN-2 | #61 | P2 | W2 L2-ACCOUNTING |
| GF-LIN-3 | #62 | P2 | W4 L4-RESUME |
| GF-LIN-4 | #63 | P3 | W3 L3-PLATFORM |
| GF-COH-1 | #64 (lifecycle.py:47-83), plus #66 (:114-130, caller-supplied `prior`, same class, no own GF) | P2→**P3** | W6 L6-EVAL |
| GF-COH-2 | #65 | P3 | W6 L6-EVAL |
| GF-SEC-1 | #95 | P2 | W3 L3-SANDBOX |
| GF-SEC-1b | #96 | P3 | W3 L3-SANDBOX |
| GF-SEC-1c | #98 | P3 | W5 L5-FEEDBACK |
| GF-SEC-2 | #99 | P2→**P3** | W5 L5-FEEDBACK |
| GF-SEC-3 | #101 | P3 | W3 L3-SANDBOX |
| GF-SEC-4 | #100 | P3 | W5 L5-GATEWAY |
| GF-SEC-5 | #102 | P3 | W3 L3-SANDBOX |
| GF-SEC-6 | #103 | P3 | W5 L5-GATEWAY |
| GF-SEC-7 | #104 | P3 | W1 L1-QUAL |

Gap-fill defects with no GF ID:
- authority: #54, #55, #56, #59 (destructive_authority.py:398-426; only textually near GF-AUTH-2's "substring tests")
- plan: #73–#78
- quality: #86–#89, #91–#94
- tripwire: #97

Original index (severities as first reported; CODE-AUDIT is authoritative):

| ID | Sev | Location | One line |
|---|---|---|---|
| GF-PLAN-1 | P2 | `plan/static_admission.py:120-129`, `obligation.py:89-102` | one criterion bound twice in a story is admitted |
| GF-PLAN-2 | P2 | `run.py:681-685` ✓, `drift.py:60-68` | drift is never attributed (`completed={}`) |
| GF-PLAN-3 | P2 | `static_admission.py:32-40` | `engine_digest` omits transitive deps |
| GF-PLAN-4 | P2 | `static_admission.py:65-79,298-299` | the admission result is not bound to `plan_hash` |
| GF-PLAN-5 | P2 | `static_admission.py:96-99,246-251` | a plan omitting an approved contract is admitted |
| GF-PLAN-6 | P3 | `journal/format3.py:147-148`, `story_runner.py:155-158` | admission is never journaled |
| GF-QUAL-1 | P1→P2 (verified) | `quality/test_execution.py:273-377`, `relevance.py:210-215` | coverage is blind to import-time and subprocess execution |
| GF-QUAL-2 | P1→P2 (verified) | `quality/test_execution.py:21-23` ✓ (docstring) + `_UNITTEST_RUNNER` (result-set write) | the result set is written by the untrusted test process |
| GF-QUAL-3 | P2 | `test_execution.py:99-118,388-398`, `errors.py:8` ✓ | subject JSON aborts the run |
| GF-QUAL-4 | P2 | `quality/vacuity.py` (neutralise, evaluate) | vacuity attribution is not controlled |
| GF-QUAL-5 | P2 | `test_execution.py:233-244,307-314`, `adequacy.py:60,80-81` | INTEGRATION import failure never blocks |
| GF-QUAL-6/7 | P2 | `relevance.py:101-113`, `vacuity.py:103-125,204-208` | renames/binary invisible; non-UTF-8/copytree errors escape |
| GF-QUAL-8 | P3 | `test_execution.py:197-206`, `control/owner.py:142-144` | a self-inflicted UNRUNNABLE is ENVIRONMENT and retryable |
| GF-AUTH-1 | P1→P2 (verified) | `tests/v2/sealing_gate.py:28-32` ✓, `tests.yml:76` ✓ | the live destructive-authority check and checker calibration are gated out of `unit` |
| GF-AUTH-2 | P1→P2 (verified) | `validation/v2/destructive_authority.py:259-302` | derivation uses exists-semantics and substring tests |
| GF-AUTH-3/4/5 | P2 | `destructive_authority.py:33` ✓, `:36-238`, `:64,427-430` | discovery fails open; scope gaps; signal-0 has no POSIX guard |
| GF-AUTH-6 | P2 | `validation/v2/cleanup_authority.py:199-211` ✓ | the Windows table reader fails open to `{}` |
| GF-AUTH-7 | P2 | `validation/v2/v1_evidence_guard.py:39-41` ✓ | v2.x released evidence is unguarded |
| GF-AUTH-8 | P2 | `validation/v2/except_boundaries.py:36-127` | 5 swallow shapes pass falsely (no live instance) |
| GF-AUTH-9/10 | P3 | `cleanup_authority.py:214-231`; `qualification/authority_limits.py:113,427-428` | no child≥parent birth check; `__builtins__` bypass |
| GF-LIN-1 | P1→P2 (verified) | `app/lineage.py:264,287` ✓ | a TZ/locale change → a live claim is superseded |
| GF-LIN-2/3/4 | P2/P2/P3 | `lineage.py:665-734`, `run.py:481-488`, `lineage.py:346-349` | emptied run = 0 spend; superseded `--parent`; raw OSError |
| GF-COH-1/2 | P2/P3 | `cohort/lifecycle.py:47-197`, `preregistration.py:84` | one-way lifecycle is a convention; evidence unbound |
| GF-SEC-1 | P2 (+P3 b/c) | `app/tripwire.py:118-124` ✓, `:36-83`; `feedback.py:78-80` | the tripwire skips silently; composite needles; stale proof cited |
| GF-SEC-2 | P2 | `app/feedback.py:68-105` | `retry_feedback` is unbounded |
| GF-SEC-3/4/5/6/7 | P3 | `diagnostics.py:41-47` ✓; `review_verify.py:306-329`; `orchestrate/adapters.py:76-84` ✓; `app/adapters.py:382-388`; `calibrations.py:5-25` | PM-8 readable; observables in findings; ReadOnlyScope; untyped Ruff read; calibration check not wired |

**Reconciliation note.** GF-SEC-1 sits beside CA#19 and is not a duplicate. GF-QUAL-3 shares a family with CA#2 (E5). GF-PLAN-3 is a
hazard input to F5. GF-AUTH-7 is the mechanical form of the CLAUDE.md manual rule. The other GF IDs map to CODE-AUDIT as above.
