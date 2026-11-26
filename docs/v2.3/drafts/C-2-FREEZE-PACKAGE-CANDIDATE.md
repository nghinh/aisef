# C-2 FREEZE-PACKAGE CANDIDATE — 2026-11-26 (DESIGN; C-2 FREEZE HOLD)

**Status:** DRAFT candidate for the owner's C-2 freeze. **C-2 PREPARATION GO; C-2 FREEZE HOLD.** Nothing here
activates production FORMAT-4 writing, makes signing optional through a silent fallback, or synthesises an owner
freeze line. This document **consolidates** the already-drafted C-2 surface into one freeze candidate and fills the
gaps the owner directive 2026-11-26 (LANE B) names; it does not re-derive what the source drafts already settle.

**Consolidates (the freeze object is the set, not this summary):**
- `docs/v2.3/drafts/A2-SIGNING-DESIGN-DRAFT.md` — the signing construction (M1–M11 facts, §3 payload, §6 V-checks, §13 limits).
- `docs/v2.3/drafts/A2-INSTALL-CONTRACT.md` — the mandatory production-installation contract (I1–I8, Decision 1/2, §7 reconciliation).
- `docs/v2.3/drafts/BUILD-REPRO-CONTRACT.md` — BUILD-REPRO-01 reproducible wheel/sdist pins.
- `docs/v2.3/drafts/FORMAT-4-FREEZE-PACKAGE.md` + `FORMAT-4-DESIGN-DRAFT.md` (frozen blob `41506829d2`, owner C-1 freeze 2026-11-26) — the writer format whose `run/begin.signer` (§4.1) makes C-2 a hard predecessor of the production flip.
- Landed code: `aisef2/journal/sign.py` (commit `648a660b`), `tests/v2/test_v23_sign.py` (RFC 8032 §7.1 vectors).

**Boundaries carried unchanged:** B2 external stays `REMOVED_FROM_V2.3_RELEASE_SCOPE_BY_OWNER`. No protected
historical evidence altered. Q0 standing blockers (`b1_bindings`, `currency_dag`, `mutation`) stay visible. No full
RC mutation campaign, master merge, production tag, or PyPI publication. Release target 26 Feb 2027, conditional on
mandatory gates.

---

## 1. `cryptography` dependency — mandatory availability for standard FORMAT-4 signing

**Landed (fact):** the Ed25519 backend is a **lazy, single-module import** — only `sign.py:_ed25519()`
(`sign.py:37-48`) imports `cryptography.hazmat.primitives.asymmetric.ed25519`; absence raises `SigningUnavailable`
with the remediation `pip install 'aisef[signing]'` and **no unsigned fallback**. `generate()` probes the backend
**eagerly** before returning a keypair (`sign.py:67-70`). Declared in `pyproject.toml:40` as the optional extra
`signing = ["cryptography>=43"]`; `dependencies = []` is a deliberate stdlib-only stance (`pyproject.toml:33`).

**C-2 decision owed — DECISION 1 (packaging at the production flip):**
- **Option 1** — promote to `[project].dependencies`: honest post-flip (the core command needs it), but breaks the
  stdlib-only stance for *every* user including verify-only/bundle-authoring users.
- **Option 2 (install-contract recommendation)** — keep the `signing` extra + fail-closed at run start: the wheel
  stays pure-Python and `--no-index --no-deps`-installable; the trust root is taken only by operators who opt in; a
  plain `aisef run` on a format-4 kernel **refuses at run start** with the exact remediation.

Version floor: `cryptography>=43` (abi3 wheels cover CPython 3.11–3.14 on all three OSes; `A2-INSTALL-CONTRACT I7`).
Import-time fail-closed is already correct (`SigningUnavailable`); C-2 must pin **where** the refusal fires (DECISION 2, §6).

## 2. Reproducible wheel/sdist + offline wheelhouse

**Landed contract:** `BUILD-REPRO-CONTRACT.md` (BUILD-REPRO-01). Wheel+sdist of a commit reproduce byte-for-byte via
`SOURCE_DATE_EPOCH=$(… release_rc.py --epoch) python -m build` + `repro_dist.py`, pinned `setuptools==84.0.0`, on
ubuntu CPython 3.11–3.14; `python -m build` builds the wheel FROM the sdist (rebuilt-from-sdist case). Packaging
contents gated by `validation/v2/packaging_check.py` (wheel+sdist hold exactly `aisef`+`aisef2`). Pinned to CI by
`tests/v23/test_v23_repro_contract.py` (23 negative fixtures).

**C-2 gap — offline wheelhouse:** the `wheel` job installs the built wheel `--no-index --no-deps` into a clean venv
and runs `installed_product_smoke.py` offline. After the production flip, every `aisef run`/`aisef demo` writes
format 4 and **needs the backend** (`A2-INSTALL-CONTRACT I5`). **No constraints file exists** (`I4`). C-2 must add a
**pinned offline wheelhouse** (a vendored `cryptography` abi3 wheel set + hashes, installed `--no-index`) so the
offline product smoke gets the backend without network, OR accept that the offline smoke covers only pre-flip
behavior. This is an owner decision (table below).

## 3. Native install/verify on Ubuntu, macOS, Windows

**CI matrix (`tests.yml:14-26`):** unit job on ubuntu 3.11/3.12/3.13/3.14, windows 3.11, macos 3.12. The unit job
`pip install "cryptography>=43"` succeeds on all three OSes (`A2-INSTALL-CONTRACT I4/I7`). The `wheel` job
(clean-venv install + smoke) runs **ubuntu-only** today (`tests.yml:145-170`).

**C-2 requirement:** signed-run install/verify must be demonstrated natively on **all three** OSes, not ubuntu-only.
`abi3` wheels exist for each; the gap is that the clean-venv smoke + signing verification is ubuntu-only. C-2 must
extend the wheel/smoke job (or add a signing-verify leg) to macOS and Windows, OR record the owner's acceptance of
ubuntu-only clean-install coverage with cross-OS covered by the unit job. V21-41(b) separately owns the Windows
0444 anchor/escrow-file creation discipline (`A2-SIGNING-DESIGN M4`: the escrow reuses the anchor codec, so A2 must
not add a second creation discipline).

## 4. RFC 8032 signing-vector verification + negative controls

**Landed (fact):** `tests/v2/test_v23_sign.py` pins RFC 8032 §7.1 TEST 1–3 (`VECTORS`, seed/pubkey/msg/sig hex) and
runs them against the **real backend** — the test **FAILS, never skips**, when `cryptography` is absent on CI
(`tests.yml:41-43`). Strictness negatives are covered in `sign.py:verify` (N2: explicit `s >= L` reject,
backend-independent, `sign.py:_L`; malformed input → `False` never raises; missing backend → `SigningUnavailable`).
Signatures are RFC 8032 deterministic (`sign.py:sign`).

**C-2 acceptance:** the three KATs + the expected-bad set (wrong-length key/sig, non-hex, `s>=L`, non-canonical
point, tampered message) are the signing-vector gate. Already present; C-2 freezes them as the ratified vector set
and adds the missing-backend V-check as a V-0 precondition (per `A2-INSTALL-CONTRACT §7.4`).

## 5. Trusted public key + off-box anchor; adversarial modification

**Construction (A2-SIGNING-DESIGN §2–§3):** one ephemeral Ed25519 keypair per run signs ONE payload
`aisef-v2-seal/1` = `{run_id, kernel_digest, journal{path,sha256,lines,head}, anchor}` at finalize
(`sign.py:seal_payload`/`seal_message`/`write_seal`). The **signature covers the anchor → the anchor covers the
manifest → the manifest covers every evidence byte**, so a consistent post-hoc rewrite of a finished run directory
is **REFUTABLE** by an operator holding the run's public key + anchor **off-box**. The private seed is never
persisted (`sign.py` Keypair). `SEAL.json` is written with the anchor's O_EXCL|O_NOFOLLOW|0444|fsync discipline and
sits **outside** the evidence manifest globs (`A2-SIGNING-DESIGN M3`: the manifest is a fixed glob list,
`run.py:426-435`).

**Existing anchor/byte-pin mechanisms C-2 builds on:** the unsigned manifest anchor (`anchor_of`, `run.py:446-448`);
`released_evidence_guard` (git-blob freeze of `closure-evidence/v2/**` at tag v2.2.0 + branch base); authority-
inventory content-addressing (`release_inventory.INVENTORY_SHA256`); range anchors (`lineage.write_anchor`). C-2
adds authenticity **on top of** consistency: `--verify` today proves consistency only and says so
(`A2-SIGNING-DESIGN M2`). Compat bounds are frozen (`M8`): CR-5 (`--expect-pubkey` on a 2.2 run is REFUTED
"unsigned", never VERIFIED-authentic), CR-6 (never retro-sign), CR-7 (format≥4 missing its signature is REFUTED,
not "an older release").

**Trust-anchor requirement:** `--expect-pubkey` takes a **value, never a path** (same as `--expect-anchor`); the
operator keeps **two 64-hex lines per run off-box** (anchor + public key). Adversarial controls: modify
journal/records/evidence/verdict → the manifest digest moves → the anchor moves → the signature over the anchor
fails under `--expect-pubkey` (the theorem of charter claim 4; proof obligations = §6 V-checks + negatives N3/CT-1).

## 6. Fail-closed before preflight, networking, journaling, paid model invocation

**Landed ordering (fact, `A2-INSTALL-CONTRACT I6`):** in `run.execute`, `RunScope.begin()` is at `run.py:630` —
**after** `RUN.started.json` (`:496-502`), the repo clone, and the provider preflight (`:608-624`, real provider
HTTP). The pre-start refusal precedent is `RunRefused` (nothing created, `run.py:478-491`). `aisef2/app/preflight.py`
runs real provider HTTP before any session; it is an identity stop on drift.

**C-2 DECISION 2 (fail-closed placement):** A2 design §4.1 says "at run start" = before `RunScope.begin` — but that
is **after** the preflight has spent real requests (`I6`). The install-contract §2.1 pins the **stronger**
placement: refuse **before `out.mkdir`** (before preflight, network, journaling, or any paid model call), so a
format-4 kernel with no backend spends **zero**. C-2 must freeze the stronger placement and add `--check` reporting
of signing readiness, so the refusal is named and costless.

## 7. Historical format-1/2/3 compatibility (the §4.10 pin)

**Fact (frozen):** format 4 adds `STORY_COMPLETED`="story/completed" and `PROVIDER_ATTESTATION`="provider/attestation"
as **format-4-only**; **formats 1-3 never admit them** (enums.py §4.10 pin comments; `format3.py` FORMAT_3_CODES /
`VOCABULARY4` stay literal, never computed from the live enum — `format4.py:15`). `KNOWN_FORMATS=(1,2,3,4)`
(`format4.py:66`); format 4 refuses to read/extend a journal of another format (`format4.py:447-491`). Readers for
formats ≤3 are unchanged (CR-3 NEW-ONLY, CR-4 classified-stricter under COMPAT-MATRIX J1–J8). CR-5/6/7 pin the
signed/unsigned boundary across releases. **No C-2 change weakens any format ≤3 reader or evidence semantic**; the
seal is additive (`SEAL.json` outside the manifest) and the signing envelope rides only format 4.

## 8. CI signing verification, expected-bad, rollback, acceptance

**Landed:** unit job installs `cryptography>=43` and runs the RFC 8032 vectors (fail-not-skip, `tests.yml:41-43`);
wheel job clean-installs + offline product smoke (`tests.yml:145-170`); process-leak discipline (owned_run) fails a
job on a leaked process even if all tests pass.

**C-2 acceptance criteria (ratify at freeze, independently reviewed):**
1. RFC 8032 KAT 1–3 pass against the real backend on every unit leg; backend-absent → the suite goes **red**, not skipped.
2. Expected-bad signing controls (tampered journal/record/evidence/verdict, wrong pubkey, `s>=L`, truncated seal) each produce **REFUTED**, never VERIFIED.
3. The signed `aisef run … --verify --expect-pubkey` round-trips natively on Ubuntu/macOS/Windows (DECISION per §3).
4. Offline product smoke obtains the backend without network (DECISION per §2) OR the owner accepts pre-flip-only offline coverage.
5. Fail-closed fires **before** preflight/network/journaling/paid-call (DECISION 2) and is covered by a test that asserts zero spend and nothing created.
6. **Rollback:** the production FORMAT-4 writer flip is revertible to format 3 without touching sealed history; C-2 freezes the flip + its revert as one reviewed window (C-1 Q5 pacing, `A2-SIGNING-DESIGN §12`).
7. Independent review of the signing construction, the install contract, and the vector set before the freeze line is issued.

---

## Owner decisions needed

| # | Decision | Options | Draft recommendation |
|---|---|---|---|
| OD-1 | Packaging at the production flip | (1) hard `[project].dependencies`; (2) keep `signing` extra + fail-closed at run start | Option 2 (A2-INSTALL-CONTRACT §2) |
| OD-2 | Fail-closed placement | "at run start" (§4.1, after preflight spend) vs "before `out.mkdir`" (before any spend) | Before `out.mkdir` (install-contract §2.1) |
| OD-3 | Offline wheelhouse for product smoke | Vendor pinned `cryptography` abi3 wheel set (+hashes) for `--no-index`; or accept pre-flip-only offline coverage | Vendor pinned wheelhouse |
| OD-4 | Cross-OS clean-install signing verify | Extend wheel/smoke job to macOS+Windows; or accept ubuntu-only clean-install (unit job covers cross-OS) | Extend to all three |
| OD-5 | FORMAT-4 production flip timing (C-1 Q5) | The flip window that makes `signer` required; C-2 must land in/ahead of it | Land C-2 in the same window as the flip, with revert |
| OD-6 | README / RELEASE-PROCESS landing (W6) | Land README repro paragraph before RC-FREEZE (default) vs ship 2.3.0 with 2.2 README | Owner decides at W6 (BUILD-REPRO-CONTRACT) |
| OD-7 | Freeze-line digests | C-2 freeze cites the blob/sha256 of each consolidated draft (as C-1 did for FORMAT-4-DESIGN `41506829d2`) | Owner issues the freeze line over the set |

## Unresolved assumptions / test obligations / integration dependencies

| # | Item | Kind | Status |
|---|---|---|---|
| A-1 | A2 design §3.2/§5/§14 still carry the superseded "vendor pure-Python Ed25519" default; landed code is the `cryptography` backend (owner pkg #1 decision 8) | Draft reconciliation | Must update design text at freeze (A2-INSTALL-CONTRACT §7.1) |
| A-2 | `verify`'s frozen signature must record that it raises `SigningUnavailable` when backend absent (not unconditional-total) | Draft reconciliation | A2-INSTALL-CONTRACT §7.2 |
| A-3 | Design §13 L2 (not-constant-time) no longer applies; replace with backend-availability + supply-chain-trust-root limitation | Draft reconciliation | A2-INSTALL-CONTRACT §7.3 |
| A-4 | §6 lacks a missing-backend V-check; add as V-0 precondition | Test obligation | A2-INSTALL-CONTRACT §7.4 |
| A-5 | `pyproject.toml:39` comment ("offline wheel smoke stays dependency-free") becomes false post-flip under either option | Doc obligation | A2-INSTALL-CONTRACT §7.6 |
| T-1 | RFC 8032 KAT 1–3 + expected-bad set | Test (landed) | `test_v23_sign.py` — present; ratify at freeze |
| T-2 | Zero-spend / nothing-created on backend-absent format-4 run | Test (owed) | New test for DECISION 2 placement |
| T-3 | Native signed round-trip on macOS + Windows | Test (owed) | Depends OD-4 |
| T-4 | Offline product smoke with backend (no network) | Test (owed) | Depends OD-3 |
| I-1 | C-2 is a hard predecessor of the FORMAT-4 production flip (C-1 Q5): `JournalWriter4` cannot go production before the A2 primitives merge | Integration dep | Blocks the flip; not blocked by this doc |
| I-2 | E7 (L2-RECORD) refactors `run.py` finalize; the seal hook attaches in the refactored `finally` (`E7 → A2-INTEGRATION [F]`) | Integration dep | A2-SIGNING-DESIGN M7 |
| I-3 | V21-41(b) rewrites the 0444 creation sites for Windows **after** A2; A2 must not add a second creation discipline | Integration dep | A2-SIGNING-DESIGN M4 |

---

**C-2 FREEZE HOLD.** This candidate prepares the freeze; the owner issues the freeze line over the consolidated set,
and only then do the packaging option, placement, wheelhouse, cross-OS matrix, and flip land — in or ahead of the
FORMAT-4 production-writer window, never before it. Production FORMAT-4 writing stays blocked; signing is never made
optional through a silent fallback.
