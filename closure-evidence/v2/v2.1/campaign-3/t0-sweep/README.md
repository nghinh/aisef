# T0 sweep of campaign 3 — what was measured, at which commit

`campaign-3/tools/sweep.py` (run by `t0-sweep.sh` under the workers' environment:
`env -i`, PATH without `opencode`, scratch HOME/XDG/TMPDIR, the machine-wide heavy lock). It runs every distinct
(null mutant, kill file) pair of the V2.1 targets once through the runner's own T0 (`run_target(..., t0_only=True)`):
235 pairs, 29 null mutants, 133 kill files. The committed record is `closure-evidence/v2/v2.1/T0-SWEEP-3.json`
(`measured_on` 206bc79); the table derived from it is `EXECUTION-ORDER-3.json`.

| pass | commit | pairs | result | files |
|---|---|---|---|---|
| first | 408e1c8 | 235 | 234 PASS, **1 FAIL** | `first-pass-at-408e1c8.jsonl`, `.log` |
| second | 206bc79 | 1 (the failed pair; the other 234 rows seeded) | PASS | `complete.jsonl`, `second-pass-at-206bc79.log` |

The one failure: `aisef2/app/confine.py` null mutant × `tests/v2/test_v21_confine.py`,
`HostGuard.test_nothing_is_copied_or_probed_outside_the_tests_directory` — the test made its faulty kernel copy by a
literal text replace (`get_paths()["purelib"]) / probe_file`) that does not match the module the runner writes
(`ast.unparse`: single quotes), so the second case never saw its fault ("AssertionError not raised"). It passed on the
committed tree and on the original tree of the same run, and failed on the null mutant, so under the runner it would
have been a T0 stop of all 20 `confine.py` targets, or — had T0 not stopped it — a false kill of every confine mutant.
Fixed in 206bc79 (the replace is a regex over either quote style); the first-pass row is kept as it was written.

The 234 rows of `complete.jsonl` that were not re-run are byte for byte the first-pass rows (the seed). Between 408e1c8
and 206bc79 the tree differs in `tests/v2/test_v21_confine.py` and three files under `campaign-3/tools/` only
(`git diff --name-only 408e1c8 206bc79`), so no target module and no other kill file changed between the two passes.

Timing: the first pass ran while the derived-records generator (p5_falsifiability, ~13 min) shared the machine; the
seconds are T0 wall-clock, used only to order a kill set (the order never decides a class, §7.1).
