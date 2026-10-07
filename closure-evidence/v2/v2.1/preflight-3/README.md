# Campaign 2 preflight at 70423f9 (2026-10-08) — the campaign-2 commit

70423f9 is v2.1/foundation with the three product tracks integrated (v21/integ: sandbox, context pack, traceability;
the sandbox's INV-MUTATION-AUTHORITY fix; four encodings; execution_order calibrated) and pilot attempt 1's evidence.
Full suite at e6b06eb (the integration before the last two fixes): 5,855 tests, 13 failures + 1 error, every one
classified in docs/v2.1/RED-SUITE.md's terms or fixed after it (the encodings and the calibration entry).

`pre3.sh` ran the T0 sweep alone under the heavy lock, at a detached checkout of 70423f9, with the workers'
environment: every distinct (null mutant, kill file) pair of the 466 V2.1 targets through the runner's own T0 —
**139 of 139 PASS**, no residue, no leak, no error; 5,094 s of T0 runs, 5,290 s wall (`pre3-sweep.log`; rows in
`../T0-SWEEP-2.json`). Against the 7577e16 sweep, the 92 pairs with the same key took 0.981× the time (median; p10
0.943, p90 1.000). The runner's own tests ran in that full suite; campaign 1's runner-1 preflight is obsolete (runner
v2 §5) and was not run.
