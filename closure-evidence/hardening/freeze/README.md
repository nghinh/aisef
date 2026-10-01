# Frozen kernel records, one file per kernel

`P19-FREEZE.json` at `closure-evidence/hardening/` is always the **current** frozen candidate: the W1 driver, the
run-copy preparation and the execution profiles read it by that path. When a kernel is superseded its record is
moved here unchanged, so the runs made against it keep a readable identity.

| file | kernel | used by |
|---|---|---|
| `P19-FREEZE-40393cd.json` | candidate 40393cda89db, product tree a2f6e76b — TDD_POLICY_V1 | every W1 run marked W1_WORKLOAD_V1 / TDD_POLICY_V1 (see `../W1-WORKLOAD-V1-POLICY-V1-MARKER.json`) |
