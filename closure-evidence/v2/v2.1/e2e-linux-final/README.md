# aisef run end to end in the Linux guest — on the FINAL product tree (2026-10-15 06:30 +07)

Closes a gap the independent verification of the B-03 round found: the earlier run (`../e2e-linux/`, 2026-10-13) ran on
commit `9f336fb` (`aisef2/` tree `427afeec…`, kernel digest `42e61270…`), **not** on the tree the mutation record and the
full suite describe (`aisef2/` tree `1d4f0156f568f240f49fbbc10e5a366a13b18f58`). Two files differ between them
(`aisef2/app/confine.py` `_sections`/`_judge`, `aisef2/runtime/process_range.py` `_Posix.abort`).

| | |
|---|---|
| run on | commit `2d01fe46f24cd17af01065a12e1fa1df41170e99`, `aisef2/` tree `1d4f0156f568f240f49fbbc10e5a366a13b18f58` (`commit.txt`); tree = `git archive` of that commit, file counts and driver bytes checked by the launcher |
| harness | `validation/v21/cli_integration/e2e_linux.sh` (unchanged), local image `aisef-sandbox-measure`, `docker run --rm --network none --user 1000:1000 --cap-drop ALL`, scripted client + loopback provider; no `opencode`, no provider, nothing pulled/built/removed |
| X1 profile | container exit 0, `passed: true`, 0 failed entries, 18 provider requests |
| hardened profile | container exit 0, `passed: true`, 0 failed entries, 0 provider requests |
| against the 2026-10-13 run | the same scenario/check names, every outcome identical |
| other containers | `goe-postgres-1`, `goe-valkey-1` not started, stopped or touched; both `Up (healthy)` after (`docker-ps-after.txt`) |
| host load | 19–26 (the analysis agents were running); X1 took 147 s vs 72 s earlier; no check depends on time |

Not shown (unchanged from `../e2e-linux/`): a real `opencode` client inside the sandbox, a real provider through the
shared network, another kernel or architecture (Docker Desktop 7.0.12-linuxkit aarch64), Windows, macOS confinement.
