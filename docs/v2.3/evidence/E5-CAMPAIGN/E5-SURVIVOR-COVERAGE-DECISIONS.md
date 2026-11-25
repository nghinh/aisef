# E5 survivor coverage decisions (owner ruling 2026-11-25 §5) — all 43 audits reviewed

Each cluster judged against the FROZEN E5 contract (W1-DESIGN §4.2/§4.3 H1–H9): is the surviving behaviour
MANDATORY there, and if so, is it asserted? Nothing is deferred silently; the audits stay append-only.

## The three named clusters (26 mutants)

**1. `_attempt` L418 `Stage.ACQUIRE→*` (12) — unreachable corner, no test owed.**
L418 is the H4 fallback label for `st.at is None`. `st.advance(Stage.ACQUIRE)` (story_runner.py:237) is the FIRST
statement inside the H1 try (:236), and `advance` itself raises only `InvariantError` — a `BaseException` H1 never
catches (§4.3 H1). So no catchable `Exception` can reach the H4 handler with `st.at is None`: the fallback is
defensive dead code for every reachable state, and H4's label contract has no unasserted mandatory case here. A test
could only drive it by corrupting internals, asserting nothing about the product. Audits stand (their "no matrix
row" ground is true; this document records the stronger one).

**2. `_attempt` L438 `Stage.MERGE→*` (10) + L439 (2) — no injection point inside the window, no test owed.**
The chain's `merge` row runs only for a fault with `st.at is MERGE` outside H3, i.e. between `merge(...)` returning
(repo back to `None`, :373) and `st.advance(Stage.POST_MERGE)` (:378). That window (:374–:376) contains one
`list.append` and typed attribute reads on merge's own returned result — no dependency call, no journal append, no
gate call: nothing the approved fault model (inject at dependency boundaries, as every F-row does) can make raise.
A fault DURING merge is H3/F12 (propagate, covered); after `advance(POST_MERGE)` it is the post-merge row
(F13–F15, covered, revert-once asserted). The mandated behaviour has no injectable trigger; H4's merge row stays
contract text for a window the product cannot fault without internal corruption. Audits stand. If a future edit
widens that window, the F5 engine's slice identity catches it.

**3. `_attempt` L317 `ObligationRole.PRESERVE→*` (2) — outside the observable contract, audit stands, flagged.**
The role reaches control only as a routing key; the CANDIDATE rows of the routing table are declared for ANY role
(aisef2/control/routing.py:15-17; `row_for` falls back to the role=None row), and `prove()` does not journal the
role (aisef2/orchestrate/proof.py:90-103: the PROBE_EVALUATED/PROOF_VERIFIED payloads carry no role). Not an H1–H9
item; no observable behaviour differs. Flagged for the final RC campaign: a role-specific CANDIDATE routing row
would make this expression load-bearing.

## Mandatory-but-unasserted behaviour FOUND and fixed within W1b (4 mutants)

**`_attempt` L445/L470 message fragments (4).** H6 prescribes the double-fault note VERBATIM:
`e.add_note(f"E5: the attempt could not be closed: {type(x).__name__}: {x}")`. The matrix asserted only that a note
names the later type — the prescribed prefix and separator were unasserted, which is exactly what these four
survivors prove. Fixed: F24 (handler path, L445) and F25 (closure path, L470) now assert the full prescribed format
(`startswith("E5: the attempt could not be closed: JournalError: ")`); matrix 29/29 green on the product.
Consequence, by the shared admissibility rule's currency check: `tests/v2/test_v23_story_lifecycle.py` changed, so
the `_attempt` round entry's `identity.kill_files` digest no longer matches the tree and the entry is now
**inadmissible (stale)** — truthful: its 30-survivor list was measured against the weaker kill set. `_attempt` is
not a B1 manifest target; its clean re-measurement belongs to the separately-authorized final RC campaign, where
the new asserts are expected to kill L445/L470 (and the audits for them become historical).

## The remaining 17 survivors — reviewed, outside the frozen contract, audits stand

* `_Stages.advance` L84 ×3: §4.2 mandates the raise and its timing ("before that stage's first write"), both
  matrix-asserted (G1/G2, R1); the message prose is not contract text.
* `run.py` L485/L487 ×3 (`--parent` refusal prose), `check_repository` L238 (temp-dir prefix), `unfinished` L411
  (report row order), L492/L493 ×2 (overwritten placeholder), L647 (dead `exist_ok` in a fresh `out`), L732 ×2
  (byte formatting outside the canonical anchor): none is prescribed by a frozen contract; each audit's
  consumer-check already names the proof.
