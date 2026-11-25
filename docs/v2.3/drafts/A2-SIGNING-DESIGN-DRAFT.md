# AISEF v2.3 — A2 EVIDENCE SIGNING DESIGN (lane L2-SIGN primitives + L2-AUTH integration) — DRAFT for the C-2 freeze

**Status:** DRAFT. Becomes frozen as contract C-2 (ACCELERATED-DELIVERY-PLAN.md §2) only by an owner freeze; after
that, a change is an appended dated amendment, never an edit. Consumers of C-2: V21-41(b), G6, B5, #6, and the
FORMAT-4 production flip (C-1 Q5: `run/begin.signer` is required in format 4, so JournalWriter4 cannot go to
production before the W2a primitives merge).

**Covers (frozen inputs):** A2 + CODE-AUDIT #10 (+#22, its verify face) + #44 + #45 + V21-49 + V21-54 (default A)
(MASTER-CHECKLIST rows; DAG §1a W2 L2-SIGN → L2-AUTH); owner decision QĐ#1 — **ALREADY DECIDED**
(ROADMAP-2.2-CHECKLIST.md:51): per-run ephemeral keypair, public half escrowed off-box like the current anchor,
transparency-log anchoring optional when infrastructure exists — this design works within it, it does not reopen it;
ROADMAP-2.2-CHECKLIST.md:116 (A2 content sketch: signature over run_id + head + anchor + kernel_digest, key outside
the writable directory); RELEASE-CHARTER claim 4 (:18-20) and gate rows :39-40 (signed `--verify` + expected-bad
controls); COMPATIBILITY-MATRIX CR-5/CR-6/CR-7, CT-1/CT-4; FORMAT-4-DESIGN-DRAFT §4.1 (the `signer` field and Q5)
and §4.10 (sealed-reader vocabulary pinning: A2's merge window precedes the `V3_VOCABULARY` pin and adds no
vocabulary of its own).

---

## 1. Measured facts that fix this design

| # | Fact | Evidence |
|---|---|---|
| M1 | The chain is unkeyed sha256: `chain_n = sha256(chain_{n-1} ‖ sha256(canonical(event_n)))` from GENESIS; `head` is the last link. The docstring states the ceiling: a tail rewritten together with its links is caught only against an anchor held outside the journal. Anyone who can write the run directory can recompute every link. | `aisef2/journal/event.py:12-15,84-90`; `journal/writer.py:56-57`; CODE-AUDIT #10 |
| M2 | `--verify` proves consistency, not authenticity, and says so: the anchor compare + its honesty note are `verify.py:167-172`; the docstring `:10-13`. The anchor itself is an UNSIGNED sha256 (`anchor_of`, run.py:446-448) of the manifest, and the anchor file is bare 64-hex (`lineage.py:829-851`). A whole-directory consistent rewrite VERIFIES unless `--expect-anchor` comes from an off-box store. | CODE-AUDIT #22; `aisef2/app/verify.py:10-13,167-172` |
| M3 | The manifest is a FIXED glob list (`RUN.json`, `RUN.started.json`, `run/journals/*.jsonl`, `sessions/*.jsonl`, `preflight/*`, review + diagnostics artifacts) written AFTER the record in the `finally`; its digest is the anchor. A new file outside those globs is invisible to the manifest — the signature artifact can live in the run directory without a self-reference problem and without touching `evidence_manifest`. | `aisef2/app/run.py:426-435,730-734` |
| M4 | The anchor-file codec is exactly one 64-hex line, created `O_EXCL|O_NOFOLLOW`, mode 0444, fsync'd; `read_anchor` refuses anything else. An Ed25519 public key is 32 bytes = 64 hex: the escrow file can reuse this codec byte-for-byte. The 0444 creation sites (`lineage.py:335,839`) are the ones V21-41(b) rewrites for Windows AFTER A2 (DAG edge `A2 → V21-41(b) [F]`) — so A2 MUST NOT add a second creation discipline. | `aisef2/app/lineage.py:829-851`; MASTER-CHECKLIST V21-41 |
| M5 | `run/begin` today carries `{journal_format, run_id}` and is written by `RunScope.begin` (`run_scope.py:123-125`) — the exact site L2-ACCOUNTING flips to JournalWriter4. FORMAT-4 §4.1 freezes the f4 field `signer`: hex64 = sha256 fingerprint of the run's ephemeral public key, inside the hash chain (CR-7's discriminator). | `aisef2/journal/event.py:195-196`; `aisef2/runtime/run_scope.py:111-135`; FORMAT-4 §4.1 |
| M6 | `dependencies = []` is a deliberate, commented stance ("toàn bộ khung chạy bằng thư viện chuẩn") and the repo vendors no crypto package (grep ed25519/nacl/cryptography over `aisef2/` → 0 hits). CPython 3.11–3.14 stdlib offers **no asymmetric signature primitive**: `hashlib` (sha2/sha3, keyed blake2) and `hmac` are MACs — the verification key IS the forgery key — and `ssl` exposes no message-signing API. What the stdlib DOES provide is everything Ed25519 needs underneath: `hashlib.sha512`, big-int `pow`, and `secrets.token_bytes` for the seed. | `pyproject.toml:33`; grep 2026-11-25 |
| M7 | The finalize already has the hook shape: record → manifest → (cli prints `evidence_anchor` from `anchor_in`, optionally writes `--anchor-out`, exit 2 if that write fails after a finished run). E7 (L2-RECORD, W2) refactors this `finally` with golden RUN.json byte-identity; the DAG makes E7 a hard predecessor: `E7 → A2-INTEGRATION [F]` — the seal hook attaches in the REFACTORED finalize. | `aisef2/app/run.py:703-734`; `aisef2/app/cli.py:101-114`; DEPENDENCY-DAG :191 |
| M8 | The compat bounds are already frozen: CR-5 (`--expect-pubkey` on a 2.2 run is REFUTED "unsigned: a run of a release before 2.3", never VERIFIED-authentic), CR-6 (never retro-sign: v2.3 writes nothing into a 2.2 run directory except a lineage claim), CR-7 (format ≥4 missing its signature / `EVIDENCE.json` / `RUN.started.json` is REFUTED, not "an older release"; the absent-manifest-⇒-note rule stays for format ≤3 only), CT-1/CT-4 pin them as tests. | COMPATIBILITY-MATRIX.md:68-80,142-145 |
| M9 | Interrupts still run the `finally` (record + manifest written as the exception propagates), so Ctrl-C/refused-shutdown runs CAN be sealed; only SIGKILL/power-loss skips finalize entirely. Repair (`runtime/repair.py`) appends journal closers but owns no key — it can never sign. | `aisef2/app/run.py:702-734` |
| M10 | Registry mutation targets in the files this design touches (counted from `validation/v2/mutation.py`): `journal/event.py` 9, `app/lineage.py` 27, `app/verify.py` 5, `app/run.py` 19 (including `execute` — the single most expensive target of E5: 49.0h/464 mutants), `app/cli.py` 2. `journal/sign.py` has none (new file ⇒ new targets). | plan §5; E5 per_target.json |
| M11 | CLI flag discipline to mirror: `--expect-anchor` is verify-only, regex-checked 64-hex at parse (`cli.py:67-74`); `--anchor-out` is run-only, must name a new non-link path, and a failed write after a finished run is exit 2, never a lost run. | `aisef2/app/cli.py:34-44,67-74,101-114` |

---

## 2. Scope and non-goals

A2 closes exactly one gap: **a consistent post-hoc rewrite of a finished run directory must be REFUTABLE by an
operator who kept two short lines off-box** (the anchor, and now the run's public key). Charter claim 4's clause
"fails any consistent adversarial rewrite when the external anchor is trusted" is the theorem; §6 V-checks plus
negative tests N3/CT-1 are its proof obligations.

Non-goals (stated so nobody waits on this freeze for them):
- N1. **No keyed chain.** The owner sketch offers "keyed chain / signed head" as alternatives; this design chooses
  the signed head+anchor (§3). A per-event MAC key held by the writer process adds no strength against the post-hoc
  adversary (who never saw the process) and would have to live somewhere a crash could leak; one signature at
  finalize over a payload that transitively binds every evidence byte is the minimal sufficient construction.
- N2. **No transparency log.** QĐ#1 names it optional "khi có hạ tầng". The escrow is the operator's off-box store,
  exactly as the anchor's today (ANCHOR-THREAT-MODEL.md). Nothing here precludes publishing `(pubkey, anchor)` to a
  log later; the payload is already a stable, canonical JSON.
- N3. **No confinement claims.** Protecting the in-memory key from a same-user in-run process is D1/D2's problem
  (declared limitation L6). A2's adversary is post-hoc.
- N4. **No signature checks on `bundle continue`.** V21-54 default A (keep) is CARRIED at this freeze: `continue_from`
  compares `_authentic`/manifest only under `--expect-anchor`, unchanged. A2 records the predecessor's anchor in
  `continues` exactly as today (run.py:488) and adds nothing to the continue path.
- N5. **No retro-signing and no 2.2 behavior change** beyond the enumerated stricter finding QA-6 (CR-4/CR-6).

---

## 3. The construction — what exactly is signed (normative)

Options weighed once, here, so the freeze records why:

| Option | Verdict |
|---|---|
| Per-event signatures | REJECTED: the hash chain already orders and binds events; per-event signing buys nothing against the post-hoc adversary, costs a signature per append, and would change the sealed line codec `{"chain","event"}` |
| Keyed (MAC) chain | REJECTED: symmetric — whoever can verify can forge; the escrowed "public half" would be a forgery oracle, contradicting QĐ#1's keypair language and claim 4 |
| Sign the journal head only | REJECTED: leaves RUN.json, streams, preflight, review artifacts rebindable (they are outside the chain) |
| Sign the manifest anchor only | REJECTED: binds everything transitively but does not name the chain identity; a future manifest-semantics change would orphan the signature's meaning |
| **Sign `{run_id, kernel_digest, journal id, head, anchor}`** | **CHOSEN** — the owner's own sketch (ROADMAP-2.2-CHECKLIST.md:116), one signature per run, binds the chain directly AND every evidence byte transitively |

### 3.1 The seal payload and artifact

At finalize, after the manifest is written (M3, M7), the kernel MUST build:

```
payload = {
  "format":        "aisef-v2-seal/1",
  "run_id":        <str>,
  "kernel_digest": <hex64>,            # run.py kernel_digest(), the one RUN.json records
  "journal":       {"path": <str>, "sha256": <hex64>, "lines": <count>, "head": <hex64>},
  "anchor":        <hex64>,            # anchor_of(the manifest just written)
}
message   = b"aisef-v2-seal/1\n" + canonical(payload).encode("utf-8")     # product.contract.canonical
SEAL.json = {"format": "aisef-v2-seal/1", "payload": payload,
             "pubkey": <hex64>, "sig": <hex128>}                           # one JSON doc + "\n"
```

`SEAL.json` is written into the run directory root with the anchor-file discipline (`O_EXCL|O_NOFOLLOW`, 0444,
fsync; M4) and is **deliberately outside the evidence manifest** (M3): the manifest glob list is not touched, and a
test pins `"SEAL.json" not in evidence_manifest(out)["files"]`. The signature covers the anchor; the anchor covers
the manifest; the manifest covers every evidence file including RUN.json and the journal — so editing ANY evidence
byte, or the manifest, or swapping journals, breaks the chain `sig → payload.anchor → manifest → files`.

Why the rewrite fails under `--expect-pubkey`: the adversary can rewrite the journal (including `run/begin.signer`),
re-chain, rewrite RUN.json and the manifest, and re-sign — but only under a keypair THEY generate, because the
authentic private half was never persisted (§4). Their pubkey is not the escrowed one: V-3 fails. Keeping the
authentic SEAL.json instead fails V-6/V-7 (the anchor/head no longer re-derive). There is no third move.

### 3.2 The signature algorithm

Ed25519 (RFC 8032), 32-byte keys, 64-byte signatures, deterministic (no nonce to misuse). Verification MUST be
strict: reject `s ≥ L`, reject non-canonically-encoded points, reject malformed lengths — fail-closed, refusal
before arithmetic. Cofactorless verification equation (the signer is our own kernel; RFC 8032 §7.1 vectors plus
negative vectors pin the implementation). The implementation decision (vendored pure-Python vs dependency) is the
owner question QA-1, default vendored — see §5.

---

## 4. Key lifecycle (QĐ#1, normative)

1. **Generation — at run start.** `run.execute` generates the keypair (`secrets.token_bytes(32)` seed) BEFORE
   `RunScope.begin`, and hands `signer = sha256(pubkey_bytes).hexdigest()` to RunScope so the f4 `run/begin` carries
   it inside the chain (M5; FORMAT-4 §4.1). One keypair per run, never reused, never derived from anything.
2. **Private half — never persisted.** It exists only in kernel-process memory: never written to any file, never in
   an env var, never passed to a child process, never in a prompt or log. The run that loses its process (SIGKILL,
   power) loses the key — by design; such a run is REFUTED-as-unsigned forever (CR-7) and repair cannot sign (M9).
   Best-effort: the keypair object is dropped right after the one `sign()` call; Python cannot guarantee memory
   zeroization (declared limitation L4).
3. **Public half — escrowed off-box, the anchor's twin.** The pubkey is 64 hex = the existing escrow codec (M4):
   - printed in the run's final output next to `evidence_anchor`, as `evidence_pubkey`;
   - optionally written by `--pubkey-out FILE` with exactly `--anchor-out`'s contract (new file, not a link,
     `lineage.write_anchor` reused verbatim — zero new creation sites, M4/V21-41(b); failed write after a finished
     run ⇒ exit 2, M11).
   "Off-box" MEANS what ANCHOR-THREAT-MODEL.md already defines for the anchor: a store that no process of the run
   host's developer/operator user can write (another machine, an append-only service, a printout). The kernel cannot
   verify off-box-ness; `--verify` says so in its note, exactly as the anchor note does today (verify.py:170-172
   precedent). Operator guidance (docs): keep `(anchor, pubkey)` together; two 64-hex lines per run.
4. **Destruction.** Process exit. Nothing to revoke: the key signs exactly one payload and identifies exactly one run.

---

## 5. NEW `aisef2/journal/sign.py` — the C-2 primitive surface (frozen names)

```
generate() -> Keypair                       # Keypair(seed: bytes32) frozen dataclass; .pubkey_hex (hex64)
fingerprint(pubkey_hex: str) -> str         # sha256 of the 32 raw bytes, hex64 — THE run/begin.signer value
sign(keypair, message: bytes) -> str        # hex128
verify(pubkey_hex, message: bytes, sig_hex) -> bool    # strict RFC 8032; malformed input -> False, never raises
seal_payload(run_id, kernel_digest, journal_info, anchor) -> dict      # §3.1 payload, canonical-ready
seal_message(payload) -> bytes              # domain prefix + canonical JSON
write_seal(path, payload, keypair) -> dict  # signs, writes SEAL.json (anchor-file discipline), returns the doc
read_seal(path) -> dict                     # strict: exactly {format, payload, pubkey, sig}, unknown keys refused
```

Pure stdlib (`hashlib`, `secrets`, `json` via `product.contract.canonical`); no file I/O except `write_seal`/`read_seal`;
no wall clock. L2-ACCOUNTING's flip consumes only `generate`/`fingerprint` (via run.py's handoff); verify consumes
`read_seal`/`verify`/`seal_message`; #6's expected-bad controls consume `generate`/`sign` to build forgeries.

**Dependency decision (owner question QA-1; evaluated honestly per M6):**
- The stdlib has NO signature primitive — `hashlib`/`hmac` are MACs and a MAC cannot meet QĐ#1 (the escrowed
  verification key would forge). An asymmetric signature therefore needs either a third-party package or a vendored
  implementation.
- **Default: vendor a pure-Python RFC 8032 Ed25519 inside `sign.py`** (~150 lines: field arithmetic by big-int
  `pow`, sha512 from hashlib, strict decoding). Keeps `dependencies = []` (M6), keeps the deterministic-build and
  supply-chain posture (charter §4: offline-first, no new trust roots), is fully testable against the RFC vectors,
  and the cost profile fits: one keygen + one sign per run, a few verifies per `--verify` — tens of milliseconds
  per operation in CPython is irrelevant at one per run (measured in the primitives' own test, not asserted here).
- **Alternative (owner may choose): `cryptography` as the first runtime dependency.** Constant-time, battle-tested,
  faster — but it is aisef's first runtime dep ever, a compiled wheel (cffi + OpenSSL) on every install of a
  product whose stance is stdlib-only, and a new supply-chain trust root the charter posture avoids. Not paid, so
  not an Economics violation — this is a posture decision, which is why it is an owner question and not silent.
- Mitigation for the default's known weakness (not constant-time): the key is ephemeral and signs EXACTLY ONE
  message in its lifetime; timing attacks need repeated observations of operations under one key. Declared as L2.
  A dev-only cross-check (CI, where `cryptography` happens to be installed for other tooling) MAY compare outputs;
  it is never a runtime import.

---

## 6. `--verify --expect-pubkey` — the CLI contract (normative)

Flags (CR-12: additions only; M11 discipline):
- `--expect-pubkey HEX64` — verify-only, 64-hex regex at parse (exactly the `--expect-anchor` pattern), composable
  with `--expect-anchor`.
- `--pubkey-out FILE` — run-only, exactly `--anchor-out`'s contract.

Verification of a run whose journal declares format ≥ 4 — ALL of (each failure a REFUTED problem naming its check):

| # | Check | Refusal (shape of the problem string) |
|---|---|---|
| V-1 | `SEAL.json` exists, reads, and is strictly `{format: "aisef-v2-seal/1", payload, pubkey, sig}` | "the run declares format 4 and has no readable seal" (CR-7; also CT-4's missing-manifest/started arms) |
| V-2 | `sha256(pubkey) == run/begin.signer` (the chain's declaration) | "the seal's key is not the one the journal's run/begin declares" |
| V-3 | `--expect-pubkey` given ⇒ `pubkey == expect_pubkey` | "the seal's key is not the escrowed public key" |
| V-4 | `sign.verify(pubkey, seal_message(payload), sig)` | "the seal's signature does not verify" |
| V-5 | `payload.run_id == rec.run_id` and `payload.kernel_digest == rec.kernel_digest` | "the seal is not this run's" |
| V-6 | `payload.journal.{path,sha256,lines}` equal RUN.json's journal reference AND `payload.journal.head` equals the head of the reconstructed journal | "the seal does not name this journal" |
| V-7 | `payload.anchor` equals the anchor re-derived from the STORED manifest, which itself must equal the FRESH manifest (the existing check) | "the seal's anchor is not the evidence's" |
| V-8 | Without `--expect-pubkey`: V-1/2/4/5/6/7 still run (self-consistency); a note is added: "the seal is consistent with the journal's declared signer; authentic only given the escrowed public half (`--expect-pubkey`), kept in a store the developer cannot write" | note, not a problem (the V21-49 pattern) |

Format ≤ 3 runs (CR-5, frozen): `--expect-pubkey` ⇒ REFUTED "unsigned: a run of a release before 2.3" — never
VERIFIED-authentic, never silently ignored (CT-1 pins it). Without the flag, behavior unchanged except:
- **V21-49 closes here** (same verify.py edit, same W2c window; DAG edge `A2-INTEGRATION → V21-49 [F]`): when
  NEITHER `--expect-anchor` NOR `--expect-pubkey` is given, verify adds the note "no --expect-anchor /
  --expect-pubkey: this verdict is consistency only, not authenticity; keep the anchor the run printed
  (`--anchor-out`) outside the run directory". Notes only — no verdict change on any 2.2 corpus run (CR-4).
- QA-6 (default yes): a format ≤ 3 run directory CARRYING a `SEAL.json` is REFUTED — "a signature artifact claims a
  run of a format that is never signed" — a classified stricter finding under CR-4/CR-6 (kernel-written 2.2 runs
  cannot contain one; only a planted file does).

Interim honesty (between the C-1 production flip and this W2c landing): old verify refuses a format-4 journal
entirely ("none of the formats this reader knows") — fail-closed, never a false VERIFIED; noted, not fixed early.

---

## 7. #6 — the CI signed-verify gate + expected-bad controls (L2-CI, W2c)

`tests.yml` currently smokes run/--verify only (DAG :170). The #6 closure job (offline, fake client, no network):

1. Run the offline e2e bundle; capture `evidence_anchor`, `evidence_pubkey`, `--anchor-out`/`--pubkey-out` files.
2. **Expected-good:** `aisef run --verify --project … --out … --expect-anchor A --expect-pubkey P` ⇒ exit 0, VERIFIED.
3. **Expected-bad controls** — each MUST exit 1 AND name its reason (string-matched, not merely nonzero):
   - EB-1 edit one journal byte and re-chain consistently (scripted re-link) ⇒ V-6/V-7 ("the seal does not name
     this journal" / manifest mismatch).
   - EB-2 full consistent rewrite under a fresh keypair (rewrite `run/begin.signer`, re-chain, regenerate RUN.json,
     manifest and SEAL.json, re-sign) ⇒ V-3 under the original `--expect-pubkey` ("not the escrowed public key").
     **This is claim 4's theorem as a CI control.**
   - EB-3 delete SEAL.json ⇒ V-1 (CR-7).
   - EB-4 edit RUN.json's `delivery_verdict`, refresh the manifest, keep the authentic seal ⇒ V-7 (anchor mismatch).
   - EB-5 `--expect-pubkey` against a committed 2.2 fixture run ⇒ "unsigned: a run of a release before 2.3" (CT-1).
4. Control-positive: an untouched copy re-verifies VERIFIED (the controls prove the gate can fail, the copy proves
   it can pass — both are required or the gate is vacuous).

`tests/installed_product_smoke.py` gains the `--expect-pubkey` happy path on the installed wheel (gate row :39-40).

---

## 8. Dispositions — #10, #22, #44, #45, V21-49, V21-54

| ID | Disposition |
|---|---|
| #10 (P2, L2-SIGN) | CLOSED by §3–§5: the head and anchor are signature-bound to an off-box key; the event.py ceiling docstring is updated to say the format-4 closure (the chain stays unkeyed sha256 — the signature, not a MAC, closes the ceiling). |
| #22 (P2, L2-AUTH; duplicate of #10's surface) | CLOSED by §6: `--expect-pubkey` makes the consistent rewrite REFUTED when the escrow is trusted; the verify docstring's consistency/authenticity paragraph (:10-13) is rewritten to state the two trust levels (anchor-bound; signature-bound) and their exact conditionality. CR-5 keeps 2.2 consistency-only. |
| #44 (P3, L2-AUTH) | The self-referential `wall_s`/timestamp compare (`rec["usage"]` vs `usage.usage(..., rec)`) is vacuous — rec compared against a function of rec. Disposition in the same W2c verify.py window: (a) the seal now makes these fields tamper-evident (any rec edit breaks V-7), closing the tamper face; (b) the vacuous equality face: `wall_s` is cross-checked against the journal's first/last event times where events exist (real evidence), and the record's `started`/`finished` are declared "recorded, seal-bound, not re-derived" in the verify docstring. No verdict change on the 2.2 corpus (CR-4): the cross-check can only add a problem a tampered record earns. Default form QA-5. |
| #45 (P3, L2-AUTH; classified EQUIVALENT) | `spec["runspec_hash"]` read outside the try (verify.py:72): folded into the try in the same window — one line, verdict unchanged by the audit's own classification (the generic catch-all already REFUTED with a finding); no new test owed beyond the existing suite. |
| V21-49 | CLOSED by §6's consistency-only note + `--anchor-out` reminder (O-8 verbatim). |
| V21-54 | Default A (keep) CARRIED at this freeze (owner package #1 item 5): `bundle continue` semantics untouched (§2 N4). If the owner reverses to B/C at the freeze, that is L2-AUTH `bundle_cli.py` work in the same W2c window; C is excluded unless versioned (DAG :458). |
| #6 | The A2 part (6b, L2-CI) is §7. The non-A2 part (6a) is L1-CIGOV's, already in W1 (DAG :130). |

---

## 9. Compatibility (the COMPAT-MATRIX bound, per artifact)

| Artifact | 2.2.0 readers | Class |
|---|---|---|
| Every format ≤3 run directory | Verdict and problems unchanged (CR-4); new notes only (V21-49, V-8) | MUST-READ-UNCHANGED |
| `SEAL.json`, `evidence_pubkey`, `--pubkey-out`, `--expect-pubkey` | Did not exist in 2.2; a 2.2 verify never sees SEAL.json (outside the manifest globs, M3) | NEW-ONLY (CR-3 spirit); no migration exists or is owed |
| `run/begin.signer` | Format-4 field, frozen by C-1 (FORMAT-4 §4.1); a 2.2 reader refuses the whole f4 journal loudly | NEW-ONLY behind the format number |
| 2.2 runs + `--expect-pubkey` | REFUTED "unsigned: a run of a release before 2.3" | CR-5, pinned CT-1 |
| f4 run missing seal/manifest/started | REFUTED, never "older release" | CR-7, pinned CT-4 |
| Anchor file + claim file codecs | Byte-identical; the pubkey escrow REUSES the anchor codec (M4) | MUST-READ-UNCHANGED (CR-10) |
| 2.2 run dir carrying a planted SEAL.json | REFUTED (stricter finding, classified) | CR-4 clause; QA-6 default |

Never retro-sign (CR-6): no code path writes a key, seal, or signature into a predecessor or any 2.2 directory;
the only cross-directory write stays the lineage claim.

---

## 10. Tamper negative-test catalogue (`tests/v2/test_v23_sign.py`, `test_v23_seal_verify.py`)

Each MUST fail for the named reason; red-before where it is a behavior change.

| # | Case | Expected |
|---|---|---|
| N1 | RFC 8032 §7.1 vectors (positive) + bit-flipped sig/message/pubkey | sign/verify exact; each flip ⇒ `verify` False |
| N2 | `s ≥ L` signature; non-canonical point encoding; wrong-length inputs | False, never an exception (strictness; fail-closed) |
| N3 | **Claim-4 theorem:** full consistent rewrite under attacker keypair (EB-2 as a unit test) | REFUTED at V-3 with `--expect-pubkey`; REFUTED at V-2/V-6 when the attacker keeps the authentic seal |
| N4 | Evidence edited after sealing, manifest refreshed, authentic seal kept | REFUTED at V-7 |
| N5 | SEAL.json deleted from an f4 run | REFUTED at V-1 (CR-7); the same directory as f3 fixture: unaffected |
| N6 | SEAL.json with unknown keys / wrong format id / truncated | `read_seal` refuses; REFUTED "no readable seal" |
| N7 | `--expect-pubkey` on a 2.2 fixture run | REFUTED "unsigned: a run of a release before 2.3" (red-before: today `--expect-pubkey` is an unknown flag) |
| N8 | signer in run/begin ≠ sha256(seal pubkey) | REFUTED at V-2 |
| N9 | Seal of run A copied into run B (payload run_id/journal mismatch) | REFUTED at V-5/V-6 |
| N10 | f3 directory with a planted SEAL.json | REFUTED (QA-6), classified stricter finding; red-before |
| N11 | `--pubkey-out` to an existing path / unwritable volume after a finished run | exit 2, run record intact (M11 mirror) |
| N12 | SIGKILL before finalize (fixture: directory without seal, journal f4, torn or whole) | REFUTED-as-unsigned; never VERIFIED; spend verdicts unchanged (E2's lane, not ours) |
| N13 | `evidence_manifest` over a sealed run | `"SEAL.json"` not among its files (the self-reference pin, M3) |

---

## 11. F5 qualification plan (KERNEL-COUPLING-01 — which registry targets re-open)

Two batches, each ONE measurement (LÔ discipline):

**Batch W2a (primitives):** `aisef2/` bytes change in `journal/sign.py` (new), `journal/event.py` (docstring),
`app/lineage.py` (docstrings), `arch/enums.py` (2 members, riding this window per FORMAT-4 §7 default).
- Re-open: event.py's 9 targets (`Event`, `validate`, `decode`, `carried`, `_cites`, 4 rule fns) and lineage.py's 27
  (incl. `read_anchor`, `claim`, `lineage_account`) — docstring-only edits, so the engine's own identity derivation
  decides MEASURED vs VERIFIED_REUSE; never asserted here. 0 UNRESOLVED; known-bad still FAIL.
- NEW targets registered: `journal/sign.py::{generate, fingerprint, sign, verify, seal_payload, seal_message,
  write_seal, read_seal}` with kill file `tests/v2/test_v23_sign.py`. Mutant classes each killed by a named row:
  drop the `s ≥ L` check ⇒ N2; wrong domain prefix ⇒ N1/N3; fingerprint over hex not raw bytes ⇒ N8; `read_seal`
  accepting unknown keys ⇒ N6; `write_seal` without O_EXCL ⇒ N11-family.

**Batch W2c (integration, inside CORE-2's successor batch):** `app/{verify,run,cli,demo}.py`.
- Re-open: verify.py's 5 targets (all), run.py's 19 — **including `execute`, the 49h top-cost target (M10)** — and
  cli.py's 2. NEW targets for the seal hook (`run.py` seal emission) and verify's V-check branch, kill file
  `test_v23_seal_verify.py` (invert V-3 ⇒ N3; skip V-7 ⇒ N4; treat missing seal as note ⇒ N5).
- **Cost flag for the owner (pre-freeze):** this batch re-opens `run.py::execute`; per plan §5a the execution-order
  lever (67.8% measured on bounded targets) SHOULD be owner-signed before this batch measures, or it pays E5-scale
  wall time. Same flag FORMAT-4 §10 raises for CORE-2 — the two batches should not both pay `execute` separately:
  the integrator schedules A2-INT's measurement WITH the CORE-2 successor batch that already re-opens run.py.

---

## 12. File-touch list — the single-writer schedule (DAG §4; A2 edits ONLY these)

**W2a, lane L2-SIGN** (its DAG row: `aisef2/journal/event.py`; NEW `aisef2/journal/sign.py`; `aisef2/app/lineage.py`):
| File | Edit |
|---|---|
| NEW `aisef2/journal/sign.py` | §5 entire |
| `aisef2/journal/event.py` | docstring ceiling paragraph ONLY (the format-4 signature closure note). No code, no vocabulary: the `V3_VOCABULARY` pin is L2-JOURNAL's and lands AFTER this merge (FORMAT-4 §9) — A2 must merge first and add no EventType reads |
| `aisef2/arch/enums.py` | +`PROVIDER_ATTESTATION`, +`STORY_COMPLETED` (FORMAT-4's two members, riding L2-SIGN's window per its §7 default; integrator logs the single-writer exception) |
| `aisef2/app/lineage.py` | `write_anchor`/`read_anchor` docstrings generalized to "one 64-hex escrow line (an anchor, or a run's public key)". No behavior change; no new creation site (M4 — V21-41(b) then fixes 0444-on-Windows once, after A2) |
| NEW `tests/v2/test_v23_sign.py` | N1/N2/N6 + vectors fixture |

**W2c, lane L2-AUTH** (after E7 merges run.py [F] and after the C-1 flip):
| File | Edit |
|---|---|
| `aisef2/app/run.py` | seal/anchor hook ONLY (the DAG row's own words): keypair generation at run start, `signer` handoff to RunScope, `write_seal` after the manifest write in E7's refactored finalize, `evidence_pubkey` in the result |
| `aisef2/app/cli.py` | `--expect-pubkey` (verify-only, 64-hex), `--pubkey-out` (run-only, `--anchor-out` mirror incl. exit 2) |
| `aisef2/app/verify.py` | format-4 read via the C-1 reader's delegation; V-1..V-8; CR-5/CR-7 refusals; V21-49 note; #44 (b)-form; #45 one-liner; docstring rewrite (§8) |
| `aisef2/app/demo.py` | print `evidence_pubkey`; the demo table's verify column exercises `--expect-pubkey` on its own run |
| NEW `tests/v2/test_v23_seal_verify.py` + `tests/v2/fixtures/**` (f4 sealed run, tampered copies, 2.2 run reused) | N3–N13 |

**W2c, lane L2-CI:** `.github/workflows/tests.yml`, `tests/installed_product_smoke.py` — §7.

**NOT A2's (contract consumers, named so the diff reviewer flags any A2 edit to them):**
`aisef2/runtime/run_scope.py` (signer parameter + JournalWriter4 flip — L2-ACCOUNTING, consuming
`sign.fingerprint`), `aisef2/journal/format4.py` (the `signer` schema — L2-JOURNAL, frozen at C-1),
`aisef2/journal/{writer,format2,format3,compat}.py` (sealed; NO edit), `aisef2/app/bundle_cli.py` (V21-54 keep ⇒
NO edit), `aisef2/runtime/repair.py` (cannot sign; NO edit).

**Pacing (the C-1 Q5 bound, restated normatively):** A2 primitives (W2a) MUST merge before the JournalWriter4
production flip, because f4 `run/begin.signer` is REQUIRED and its value is `sign.fingerprint`. The flip MUST NOT
wait for A2-INT (W2c): C-2 hands L2-ACCOUNTING `generate`/`fingerprint` at the W2a merge. If W2a slips past
CORE-2, the flip slips with it (FORMAT-4 Q5's default), never `signer`-as-optional.

---

## 13. Declared limitations (written into the sign.py docstring and the verify note)

- L1. **Conditional authenticity.** `--expect-pubkey` proves authenticity exactly as far as the escrowed value came
  from a store the developer cannot write (ANCHOR-THREAT-MODEL). The kernel cannot verify the escrow's custody; the
  note says so (the anchor's precedent, verify.py:170-172).
- L2. The default implementation is not constant-time (QA-1). Exposure is bounded by design: one signature per
  ephemeral key, ever. Swapping the internals for `cryptography` later changes no C-2 surface.
- L3. A run killed before finalize is REFUTED-as-unsigned forever; repair cannot sign (M9). Fail-closed, and the
  honest cost of "private half never persisted".
- L4. Python cannot zeroize memory; the private key's lifetime ceiling is the kernel process's.
- L5. The seal binds bytes, not truth: a kernel compromised DURING the run signs its own lies. A2 defeats the
  post-hoc rewrite only — exactly claim 4's scope ("consistent adversarial rewrite").
- L6. Until D1/D2, an in-run same-user process could in principle read the key from kernel memory (ptrace) and
  forge within the run window. Out of A2's scope; named so SECURITY owns it knowingly.
- L7. The seal does not authenticate the bundle's content or the kernel binary beyond recording their digests:
  `kernel_digest` is self-reported by the signing process.
- L8. Format ≤3 runs are consistency-only forever (CR-5); v2.3 never upgrades or re-claims them (CR-6).

## 14. Open questions for the freeze (each with its default; none is a STOP unless marked)

- **QA-1 (OWNER, the dependency decision):** vendored pure-Python RFC 8032 Ed25519 in `sign.py` (DEFAULT — keeps
  `dependencies = []`, no new supply-chain root, L2 declared) vs `cryptography` as the first runtime dependency
  (constant-time, compiled wheel, posture change). §5 carries the full evaluation. Not paid either way.
- **QA-2:** artifact name/id `SEAL.json` / `"aisef-v2-seal/1"` (default as specified; CR-10 gets a new id, dual
  reader n/a — the artifact is new).
- **QA-3:** pubkey escrow UX — printed at end-of-run + optional `--pubkey-out` (default, the anchor's exact
  pattern) vs REQUIRING `--pubkey-out` for f4 runs (stricter; rejected by default: stdout is already the
  operator channel, and a mandatory flag breaks every existing invocation).
- **QA-4 = V21-54:** default A (keep) carried (§8). Asked once in the owner package, not re-asked here.
- **QA-5:** #44's (b)-form — journal-span cross-check for `wall_s` + "recorded, seal-bound, not re-derived" for
  the timestamps (default) vs note-only.
- **QA-6:** planted SEAL.json in a format ≤3 directory ⇒ REFUTED as a classified stricter finding (default) vs
  note-only. Default refuses: a signature artifact claiming an unsigned format is a real adversarial shape (CR-6).
- **QA-7:** a second "birth seal" at run start (over `run/begin`'s head) so SIGKILLed runs retain start-authenticity —
  default NO (YAGNI: it cannot make the run VERIFIED, L3 stands either way; complexity without a consumer).
- **QA-8 (schedule, = FORMAT-4 Q5):** if W2a slips past CORE-2, the flip slips (default); `signer`-as-optional is
  refused (violates CR-7's discriminator).
