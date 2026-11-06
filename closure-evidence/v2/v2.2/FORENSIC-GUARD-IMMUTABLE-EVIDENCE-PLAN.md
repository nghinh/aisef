# Plan — move the HistoricalAttempt4 forensic guard to immutable evidence (owner #5)

Owner #5 (2026-11-06): *prepare a plan to move the forensic guard to immutable evidence; keep the verification meaning; do not merely skip the test to reach PASS.* **Plan only — nothing changed.**

## 1. What the guard checks today, and why it is fragile

`c2_delivery_experiment.external_problems(n)` ([validation/qualification/c2_delivery_experiment.py:1033](../../../validation/qualification/c2_delivery_experiment.py)) asserts, for a historical attempt `n`, that *this machine's* external evidence holds. Four sub-checks:

1. the preserved **external copy**'s `MANIFEST.sha256` equals the committed manifest, and every listed file's checksum matches;
2. the preserved **`attempt-n.git`** passes `git fsck --full --strict` and contains every commit the journal names;
3. every journal-named object id is present in the preserved git dir;
4. **the developer client's store has no session created after the run ended** — opens the *live* `~/.local/share/opencode/opencode.db` and fails if `max(time_created)/1000 > attempt-n.finished`.

Sub-checks 1–3 read **committed/preserved, immutable** artifacts — they are correct and stable. **Sub-check 4 reads a live, shared, append-only resource.** The opencode store is the developer's real client DB; it legitimately grows every time anyone runs opencode on this box. So sub-check 4 trips on *any* legitimate client activity after `attempt-n.finished`, not only on tampering. The Đợt-2 paid B1/B7 canary (owner-approved) wrote sessions on 2026-11-05/06; attempt-4 finished 2026-10-03 → the local full suite's one failure (DO-CUOI §3a). It is machine-local (guarded by `preserve_root()/attempt-4-evidence`, absent on CI) and 0% caused by any code diff.

**Root cause of the fragility:** the check conflates two very different propositions —
- *(intended)* "attempt-n's external evidence, including the client-store state it rested on, is intact and un-tampered";
- *(implemented)* "nobody has used this opencode install since attempt-n ended".
The second is not a security property; it is an accident of reading a live file.

## 2. The verification meaning to preserve (NOT skip)

The guard exists so a reviewer can trust that attempt-n's *external* footprint (the git objects the journal names, and the client sessions that produced them) is exactly what attempt-n recorded — that no one back-filled or rewrote the external record afterwards. The immutable-evidence version must keep **that** meaning. It must still fail if attempt-n's own preserved sessions are altered, missing, or inconsistent with the journal. It must NOT fail merely because the live store grew.

## 3. Options

### Option A — freeze the attempt-n store footprint into the preserved evidence (recommended)
At preservation time (or as a one-time, owner-approved backfill under §5 provenance rules), capture the **attempt-n session rows** the journal references — the specific `session` ids attempt-n used, with their `time_created` and the `part`/message rows that belong to them — and write them, plus a digest, into the preserved external copy (alongside the existing `MANIFEST.sha256`). The guard then:
- reads the **frozen snapshot**, not the live DB;
- verifies the snapshot's digest (immutable, like sub-checks 1–3);
- cross-checks that every session id the attempt-n journal names appears in the snapshot with the recorded `time_created ≤ finished` and unchanged content.

This keeps the exact meaning ("attempt-n's client-store footprint is the committed one") and is immune to later legitimate client activity. The live store is no longer read.

### Option B — scope the live check to attempt-n's own session ids (lighter, weaker)
Keep reading the live DB but change the predicate from "no session newer than `finished`" to "every session id attempt-n's journal names still exists with its recorded `time_created ≤ finished` and unchanged digest; ignore all other rows." This removes the false trip (newer unrelated sessions no longer matter) while still catching deletion/rewrite of attempt-n's own sessions. Weaker than A (still reads a mutable file; a row could be deleted and the DB vacuumed), and still depends on the box keeping that opencode install.

**Recommendation: Option A.** It converts sub-check 4 into the same immutable-artifact shape as sub-checks 1–3, which is the whole point of owner #5.

## 4. Provenance constraint (ties to owner #4)
The attempt-n snapshot must capture **attempt-n-era** state. If a faithful attempt-4 store snapshot was **not** captured at the time (it was not — the current preserved external copy covers the git repo/dir, not `opencode.db`), we **cannot** fabricate one from today's contaminated live store. In that case Option A is applied **going forward** (future attempts snapshot their store), and for attempt-4 specifically we fall back to **Option B scoped to the journal-named session ids** (which exist in the committed journal and can be verified against whatever of them survives in the store), plus an explicit evidence note that attempt-4's full store snapshot predates this policy. No back-dating, no fabrication (owner #4/#5).

## 5. Regression coverage
- A unit test that builds a temp store with (a) exactly attempt-n's session ids ≤ finished → PASS, (b) a deleted/renamed attempt-n session → FAIL, (c) a *newer unrelated* session added → **PASS** (the bug this fixes), (d) an attempt-n session whose content digest changed → FAIL.
- Keep the existing absent-copy / dirty-fsck assertions (the test's first two `assertTrue`s already cover those and must stay red-on-tamper).

## 6. Status
Plan only. No change to `external_problems`, the test, or any evidence. Awaiting owner go to implement (and, for the attempt-4 backfill, the §4 provenance decision which overlaps owner #4's reseal governance).
