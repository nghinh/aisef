# AISEF v2.3 — A2 MANDATORY PRODUCTION-INSTALLATION CONTRACT — DRAFT (2026-11-26)

**Status:** DRAFT, proposed for the C-2 freeze. Owner directive 2026-11-26 P2: this is the thing that must be
resolved **before enabling format-4 signing** in production — the maintained `cryptography` backend (no vendored
Ed25519, strict fail-closed, external public-key trust) is decided; what is NOT yet decided is how an
**installation** of aisef is guaranteed to carry, pin, and prove that backend. One recommended option per question,
honestly argued; every option's full cost is spelled out so the freeze records why.

**Reads with:** `docs/v2.3/drafts/A2-SIGNING-DESIGN-DRAFT.md` (the construction; §5 dependency decision, §12
pacing, §13 limitations), `aisef2/journal/sign.py` (landed 2026-11-26, commit 648a660b), `pyproject.toml:33-40`,
`.github/workflows/tests.yml:41-43,149-166`, `tests/installed_product_smoke.py`,
`docs/v2.1/ANCHOR-THREAT-MODEL.md`.

---

## 1. Measured facts this contract stands on

| # | Fact | Evidence |
|---|---|---|
| I1 | The backend is landed as a **lazy, single-module import**: only `aisef2/journal/sign.py` imports `cryptography`, and only inside `_ed25519()`. Missing backend ⇒ `SigningUnavailable` ("evidence signing needs the 'cryptography' package (pip install 'aisef[signing]'); there is no unsigned fallback"). | `sign.py:37-48` |
| I2 | `generate()` probes the backend **eagerly** — `_ed25519()` at `sign.py:69` runs before a `Keypair` is returned ("fail closed BEFORE a run starts relying on a keypair it cannot sign with"). | `sign.py:67-70` |
| I3 | `dependencies = []` is a deliberate, commented stance ("toàn bộ khung chạy bằng thư viện chuẩn"); the `signing` extra's comment already names this contract's fork: "it becomes a hard dependency only if the owner issues that decision at the C-2 freeze." | `pyproject.toml:33,35-40` |
| I4 | CI installs the backend **only** in the `unit` job (`pip install "cryptography>=43"`, unpinned above the floor); the `wheel` job installs the built wheel `--no-index --no-deps` into a clean venv and runs the end-to-end product smoke from it, on **ubuntu only**. No constraints file exists anywhere in the repo. | `tests.yml:43,149-166`; `find`/`grep` 2026-11-26 |
| I5 | `tests/installed_product_smoke.py` runs the installed `aisef run` `--check`/run/`--verify` plus `aisef demo` offline. After the production flip (JournalWriter4), every one of those runs writes format 4 and therefore **needs the backend** — so the offline product smoke needs a networkless way to get `cryptography` into the venv **under either option below**. | `installed_product_smoke.py:106-151`; FORMAT-4 §4.1 (signer required) |
| I6 | In `run.execute`, `RunScope.begin()` is at `run.py:630` — **after** `RUN.started.json` is written (`:496-502`), the repository clone, and the provider preflight (`:608-624`, real provider HTTP). The pre-start refusal precedent (`RunRefused`, nothing created) is `run.py:478-491`. | `aisef2/app/run.py` |
| I7 | `cryptography>=43` ships abi3 binary wheels (one wheel covers CPython 3.11–3.14) for manylinux x86_64/aarch64, musllinux, macOS (arm64/x86_64/universal2) and Windows (amd64/win32). The `unit` matrix already installs it successfully on all three OSes and on 3.11–3.14 (Linux). Availability is good on every claimed platform; the sdist-compile fallback (Rust toolchain) is the case the offline test must **exclude**, not support. | `tests.yml:14-26,43`; PyPI wheel sets |
| I8 | The RFC 8032 §7.1 vectors are already pinned in-repo: `tests/v2/test_v23_sign.py:21-…` (TEST 1 seed `9d61b19d…`, pubkey `d75a9801…`). That test runs against the real backend and FAILS (never skips) when it is missing. | `test_v23_sign.py`; `tests.yml:41-43` |

---

## 2. Decision 1 — packaging at the production flip (ONE option)

The flip = the moment JournalWriter4 becomes the production writer (C-1 Q5 / A2 design §12 pacing). From that
moment `aisef run` and `aisef demo` cannot complete without the backend (I5).

| | Option 1 — promote to `[project].dependencies` | Option 2 — keep the `signing` extra; fail-closed at run start |
|---|---|---|
| Supply-chain posture | Breaks the commented `dependencies = []` stance (I3): every install of a stdlib-only product pulls a compiled OpenSSL binding; a new trust root for **all** users, including verify-consistency-only and bundle-authoring users who never run | Stance intact: aisef's own wheel stays pure-Python, installable `--no-index --no-deps` anywhere forever; the trust root is taken only by operators who opt in (`pip install 'aisef[signing]'`) |
| User surprise | None at run time; silent at install time (~a few MB of compiled wheel) | A plain `pip install aisef; aisef run` on a format-4 kernel **refuses at run start** with the exact remediation in the message (I1). Bounded, named, zero spend (see the precise claim below) — the product's house style is exactly this kind of refusal |
| Honesty of the metadata | Honest post-flip: the core command needs it, so it is a dependency | "Optional" understates post-flip reality for `aisef run`; mitigated by the refusal naming the extra, and by `--check` reporting readiness (specified below) |
| CI complexity | Wheelhouse required for the offline smoke (I5). `pip download` resolves aisef's deps | Wheelhouse required for the offline smoke (I5) — **the same machinery**; plus one extra expected-bad control (the no-backend refusal), which Option 1 cannot even express |
| Wheel availability 3.11–3.14, 3 OSes | Fine (I7) — but an install on a platform **without** a wheel (new arch, no Rust toolchain) now cannot install aisef at all | Fine (I7) — and a wheel-less platform can still install aisef and use everything except signing/format-4 runs |

**RECOMMENDED: Option 2** — keep the `signing` extra and fail closed at run start. The CI cost is identical
post-flip (both options need the wheelhouse, I5), so the decision is pure posture — and the repo's posture is
written down at `pyproject.toml:33` and in the charter (offline-first, no new trust roots for users who did not
ask for them). A named refusal with its one-line fix, before any spend, is cheaper than a compiled trust root on
every install.

### 2.1 The run-start abort — the claim, verified and stated precisely

The directive's claim: "sign.generate() is called before RunScope.begin per the A2 design §4.1, so the run aborts
before any work." Verified against the design text and the landed code, with one needed sharpening:

- **True as to the journal and all story work.** Design §4 item 1 ("§4.1"): generation happens in `run.execute`
  "at run start … BEFORE `RunScope.begin`". Landed `generate()` raises `SigningUnavailable` eagerly (I2). So a
  format-4 run on a backend-less machine aborts before `run/begin` is journaled, before any story, agent call, or
  commit.
- **NOT automatically true as to all spend.** The design's literal normative bound is only "before
  `RunScope.begin`" (`run.py:630`) — which is AFTER `RUN.started.json`, the clone, and the **provider preflight**
  (I6). Placed literally at the latest point the design permits, a backend-less run would have already made real
  provider HTTP requests before aborting.
- **This contract therefore pins the placement (normative, W2c):** for a format-4 run, `run.execute` MUST call
  `sign.generate()` among the pre-start refusals, **before `out.mkdir` (`run.py:491`)** — alongside the existing
  `RunRefused` checks (I6). A backend-less machine then leaves **no run directory, no `RUN.started.json`, no
  provider request**; the refusal is `SigningUnavailable`'s own message (I1), surfaced with the `RunRefused` exit
  discipline. The keypair generated there is handed to `RunScope.begin` later, as design §4.1 already requires.
  (Key-exposure window grows by the clone+preflight duration; L6 already declares in-run same-user exposure out
  of scope, so this costs nothing.)
- **`aisef run --check` SHOULD additionally report backend readiness** for a format-4 kernel (ready / "signing
  backend missing: pip install 'aisef[signing]'"), so the refusal is discoverable before a paid invocation.

### 2.2 CI changes required (per option; the chosen one lands with the flip, not before)

**Both options, the shared machinery** (new; the offline product smoke cannot run format 4 without it, I5):

1. **Networked wheelhouse step** (in the `wheel` job, before any offline step):
   `pip download --dest wheelhouse --only-binary :all: -c .github/constraints/signing.txt "cryptography>=43"`.
   `--only-binary :all:` makes a missing platform wheel a loud failure, never a silent source build (I7).
2. **Offline install step** (no network from here on):
   - Option 2: `pip install --no-index --no-deps dist/*.whl` (unchanged, `tests.yml:151-152`), then
     `pip install --no-index --find-links wheelhouse cryptography` into the same venv.
   - Option 1: drop `--no-deps`; `pip install --no-index --find-links wheelhouse dist/*.whl` (the wheelhouse must
     then also hold whatever `pip download` resolved transitively for the platform).
3. The product smoke (`tests.yml:166`) then exercises the installed format-4 `aisef run` end to end, offline,
   exactly as today.

**Option 2 only (recommended), additionally:**

4. Keep one venv WITHOUT the backend and assert the expected-bad control: the installed `aisef run` on a format-4
   kernel exits nonzero **before creating the out directory**, and stderr contains "needs the 'cryptography'
   package" — the fail-closed packaging proven in CI, not asserted in prose.
5. `unit` job: `tests.yml:43` becomes `pip install -c .github/constraints/signing.txt "cryptography>=43"` (§3).
6. `pyproject.toml:39` comment ("The offline wheel smoke (--no-index --no-deps) stays dependency-free") must be
   updated at the flip: aisef's own wheel still installs dependency-free (step 2 keeps `--no-deps`), but the
   product smoke venv no longer is.

**Option 1 only, additionally:** move `cryptography>=43` from the extra to `[project].dependencies`; delete the
extra; rewrite the `pyproject.toml:33` stance comment honestly; `tests.yml:43` becomes redundant for the unit
job's own venv but stays as the pinned-constraints install.

---

## 3. Decision 2 — version policy (ONE option, recommended)

- **Floor in pyproject:** `cryptography>=43` (as landed, `pyproject.toml:40`). The floor is what user installs
  actually get; it moves only for cause (a CVE or a required API), in an aisef release, never silently.
- **Exact pin in CI:** a new constraints file **`.github/constraints/signing.txt`** (next to the workflows that
  consume it; no requirements/constraints convention exists in the repo today, I4 — this creates the one place).
  Content: `cryptography==<exact>` plus every transitive distribution `pip download` resolves for it on the CI
  platforms (possibly none on CPython), each `==`-pinned. Consumed by `tests.yml:43` (`-c`) and by the wheelhouse
  step (§2.2). Reproducibility claim: two runs of the same commit install byte-identical backend versions; the
  unpinned `>=43` of today (I4) cannot claim that.
- **Cadence:** the pin is reviewed and bumped **once per release cycle, at the RC freeze** (the moment the tree
  is re-measured anyway — LÔ discipline, no micro-bumps between), and immediately on a CVE.
- **At a cryptography CVE (the policy):**
  1. Bump the pin in `.github/constraints/signing.txt` to the first fixed release; CI re-runs the RFC vectors
     (I8) and the offline smoke — that is the whole re-qualification for a backend patch, because no C-2 surface
     changes (design §13 L2's own promise: swapping internals changes no surface).
  2. Raise the pyproject **floor** only if the CVE affects code paths aisef uses (Ed25519 sign/verify, key
     (de)serialization): then the floor moves to the first fixed version and ships as an aisef patch release,
     because the floor — not the CI pin — is what protects user installs.
  3. Existing seals are never re-signed (CR-6 stands). A verifier-side CVE does not invalidate past seals; a
     forgery-enabling CVE (an attacker can forge signatures that `verify` accepts) is assessed against charter
     claim 4 and published as a dated erratum naming the affected verifier versions — the record's discipline,
     applied to the backend.

---

## 4. Decision 3 — the offline-installation test (ONE option, recommended)

Directive: "offline installation tests on the required supported platforms." The required platforms are the
claimed ones (`pyproject.toml:23-30`, the `unit` matrix): **Linux, macOS, Windows**, Python 3.11–3.14.

**The jobs:** extend the `wheel` job's offline legs into a matrix `os: [ubuntu-latest, macos-latest,
windows-latest]` at Python 3.11 (the lowest supported — the current wheel job's choice), building once and
sharing `dist/` + `wheelhouse/` via an artifact, or rebuilding per-OS (the build is deterministic either way,
`tests.yml:136-142`). Interpreter-version coverage beyond 3.11 is already carried by the `unit` matrix's
networked `cryptography` install on 3.11–3.14 (I7) plus the abi3 wheel property (one wheel per platform covers
all four); the offline matrix does not multiply across Python versions.

**Each leg proves, with NO network after the wheelhouse step (`--no-index` throughout):**

1. `pip install --no-index --no-deps dist/*.whl` succeeds (aisef's wheel itself needs nothing — both options
   keep this true for the wheel file; under Option 1 the metadata declares the dep, so this leg uses `--no-deps`
   deliberately to prove the wheel's own installability).
2. `pip install --no-index --find-links wheelhouse cryptography` succeeds from binary wheels only.
3. The venv's interpreter, isolated: `import aisef2.journal.sign` **from the installed artifact** (the
   `installed_product_smoke.py:72-75` discipline: no module from the checkout), then
   - one full round-trip: `kp = generate(); sig = sign(kp, m); assert verify(kp.pubkey_hex, m, sig)` and one
     bit-flip `assert not verify(...)`;
   - **RFC 8032 §7.1 TEST 1** against the pinned vector (seed `9d61b19deffd5a60ba844af492ec2cc44449c5697b32691…`,
     pubkey `d75a9801…` — the exact values already committed at `tests/v2/test_v23_sign.py:21-…`, which this
     smoke reuses rather than re-typing; a wrong backend build fails here, not in production).
4. The existing offline product smoke (`tests.yml:166`) — the installed format-4 `aisef run` `--check`/run/
   `--verify` end to end, which after the flip exercises `generate`/`sign`/`write_seal` for real.
5. **The fail-closed control (Option 2):** a second venv with only `dist/*.whl` (no backend): the format-4
   `aisef run` refuses at run start, creates no out directory, and names the package (§2.2 step 4). A gate that
   cannot fail is vacuous — this is the leg that proves the refusal exists.

Implementation shape: a small signing leg added to `tests/installed_product_smoke.py` (it already owns the
installed-artifact import discipline and is already invoked per-venv), not a new harness.

---

## 5. Fail-closed inventory — every path where the backend can be absent at use time

Read from `aisef2/journal/sign.py` as landed (every observable stated; "planned" = lands in W2c per design §6/§12
— **none of the verify-side or run-side behavior below is implemented today**: `run.py`, `cli.py`, `verify.py`
contain no reference to `sign` as of 648a660b, verified by grep 2026-11-26).

| Path | Backend needed? | Observable behavior when absent |
|---|---|---|
| `generate()` | yes, **eagerly** (`sign.py:69`) | raises `SigningUnavailable` before any `Keypair` exists (I2) |
| `Keypair.pubkey_hex` (`sign.py:61-64`) | yes | raises `SigningUnavailable` |
| `sign()` (`sign.py:80-85`) | yes | raises `SigningUnavailable` |
| `verify()` (`sign.py:88-104`) | yes, but **after** the input checks | malformed input (types, hex shapes, `s ≥ L`, `sign.py:92-98`) returns **False without touching the backend**; a **well-formed** triple then raises `SigningUnavailable` at `:99` — deliberately never False, because a False there would read as "forged" (docstring `:89-91`) |
| `fingerprint()` (`sign.py:73-77`) | **no** (pure hashlib) | works on a backend-less machine — `run/begin.signer` can always be recomputed from an escrowed pubkey |
| `seal_payload` / `seal_message` (`:107-128`) | no | work (pure validation + canonical JSON) |
| `write_seal()` (`sign.py:131-143`) | yes (via `pubkey_hex` + `sign` at `:136-137`, **before** `os.open` at `:138`) | raises `SigningUnavailable` with **no file created** — a partial or unsigned `SEAL.json` cannot exist |
| `read_seal()` (`sign.py:146-162`) | no | reads and shape-checks a seal anywhere — which is exactly why the verify side below must be explicit |
| **Planned (W2c):** format-4 `aisef run` start | yes | `generate()` aborts the run; with §2.1's pinned placement, before the out directory, `RUN.started.json`, or any provider request exists |
| **Planned (W2c):** `aisef run --verify --expect-pubkey` on a backend-less machine | yes (V-4 calls `sign.verify` on a well-formed seal) | MUST be a refusal naming the missing backend ("signature verification needs the 'cryptography' package (pip install 'aisef[signing]')") — **never** a silent downgrade to a consistency-only verdict, and never REFUTED-as-forged (the `verify()` raise, not False, is what makes this expressible). **Flag: not yet implemented**; the A2 design's §6 V-check table has no missing-backend row — it needs one (a V-0 precondition) at the freeze |
| **Planned (W2c):** plain `--verify` (no flag) on a format-4 run | yes (V-8 runs V-4 as self-consistency) | the same refusal; a format-4 run has no backend-less verify path at all — consistency-only is a format-≤3 behavior, never a fallback |

---

## 6. External public-key trust (restated from design §4 item 3 + ANCHOR-THREAT-MODEL — no redesign)

- The run prints `evidence_pubkey` (64 hex) next to `evidence_anchor`; `--pubkey-out FILE` writes it with
  `--anchor-out`'s exact contract (new non-link file, `lineage.write_anchor` reused verbatim — zero new creation
  sites; failed write after a finished run ⇒ exit 2).
- **Off-box** means what `docs/v2.1/ANCHOR-THREAT-MODEL.md` already defines for the anchor: a store that no
  process of the run host's developer/operator user can write (another machine, an append-only service, a
  printout). The kernel cannot verify the store's custody — authenticity under `--expect-pubkey` is conditional
  on it (design L1), and the verify note says so, exactly as the anchor note does today (`verify.py:170-172`
  precedent).
- The threat table carries over unchanged: an attacker who can write the run directory but not the store is
  REFUTED (now at V-3: their re-signed seal is under a key that is not the escrowed one); an attacker who can
  write **both** remains undetected — the signature adds a second line to the same store, it does not change who
  must guard the store. `--expect-pubkey` takes a **value**, never a path, for the same reason `--expect-anchor`
  does.
- **What the operator gets (documentation owed at the flip):** a USAGE section — "keep two 64-hex lines per run,
  together, off-box: the anchor and the public key"; the end-of-run output showing both; the verify note text
  (V-8) stating the conditionality in one sentence; and the CVE/erratum policy of §3 as the operator-visible
  promise about the backend.

---

## 7. Design-draft vs landed-code discrepancies (reported, not fixed here)

The A2 design is still a DRAFT, so these are freeze-reconciliation items, not amendment violations:

1. **QA-1 default superseded.** Design §3.2/§5/§14 carry "default: vendor a pure-Python RFC 8032 Ed25519" and §5
   opens "Pure stdlib"; the landed `sign.py` is the `cryptography` backend per owner package #1 decision 8. The
   draft must be updated at the freeze to record the decided direction, or C-2 freezes a surface its own text
   contradicts.
2. **`verify`'s frozen signature is stale.** Design §5: "`verify(...) -> bool … malformed input -> False, never
   raises`" — unconditional under the vendored default. Landed `verify` raises `SigningUnavailable` when the
   backend is absent (deliberate, documented, and what §5's row in this contract depends on). The frozen C-2
   signature text must carry that exception.
3. **L2 (not constant-time) no longer applies.** Design §13 L2 describes the vendored default's timing weakness;
   the landed backend is constant-time. L2 should be replaced by the real limitation of the chosen direction:
   backend availability (fail-closed refusals; a platform without a wheel cannot sign) and the new supply-chain
   trust root.
4. **§6 lacks a missing-backend V-check.** No row says what `--verify` does when the backend is absent; this
   contract's §5 specifies it (refusal naming the backend) and it must enter the design as a V-0 precondition.
5. **§4.1's "at run start" is weaker than the directive's claim.** The literal bound "before `RunScope.begin`"
   permits an abort **after** the provider preflight has spent real requests (I6). §2.1 pins the stronger
   placement (before `out.mkdir`); the design should adopt it.
6. **`pyproject.toml:39`'s comment** ("The offline wheel smoke (--no-index --no-deps) stays dependency-free")
   becomes false for the product-smoke venv at the flip under either option (I5); §2.2 step 6 owns the update.

---

## 8. Becomes binding when

This contract **binds at the C-2 freeze, together with the production-flip decision** (C-1 Q5 / design §12
pacing): the chosen packaging option, the constraints file, the offline matrix, and the pinned run-start
placement all land in the same window as (or ahead of) the JournalWriter4 flip — none of it is needed, and none
of it ships, before format 4 is the production writer. **Until then the landed state stays exactly as is:** the
`signing` extra (`pyproject.toml:35-40`), the fail-closed `sign.py`, the unit job's networked
`cryptography>=43` install, and the dependency-free offline wheel smoke.
