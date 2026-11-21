# E5 readiness (read-only analysis)

[`E5-READINESS.md`](E5-READINESS.md) was written at `1e25ef84`, before the W1 tracks were merged. The integration commit
changed some of the prerequisite states it reports:

* **Merged:**
  * the recorder (track A, reviews 1–2, bounded strace observation);
  * ROUND-AUTH and the distinct v2.3 Q0 round (track D; seq-13 draft R5, not ratified);
  * lanes L1-BUILD, L1-F2, L1-TESTENV, L1-CIGOV and L1-QUAL.
* **Not merged:** L1-AUTHCHK. It moves Q0 (55/57) and turns 3 GATED tests red, so it waits at the Q0-1 boundary.
* **Unchanged:**
  * E5 still waits on L1-F5 (the F5 source rule, F5-ROUND, `in_round` / `validate(round=)`);
  * the owner's seq-13 ratification;
  * a Q0-1 ruling for the `aisef2/app/run.py:693` hunk (§3.2 B: 25 B1-manifest bindings move, so Q0 drops to 56/57);
  * an amendment for where the lifecycle kill file goes (§3.3). `tests/v23` is outside every mutation COPY root.
