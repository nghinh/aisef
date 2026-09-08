# Absolute prohibitions

This list differs from principles in that principles require judgment,
while the items below **have no exceptions** and most are enforced by
hooks rather than relying on the agent's memory.

## With source code

1. **Do not write outside the story's `write_scope`.** If you need to
   touch something else, stop and report — most likely the story was
   split incorrectly, or the scope declaration is incomplete.
2. **No `git add -A`, no `git add .`.** Stage only the paths the story
   touches. Bulk commands swallow stray files and changes from other
   stories.
3. **Do not put secrets in source code, logs, or traces.** Keys,
   passwords, and tokens are read from environment variables or a secret
   store.
4. **Do not concatenate strings into queries.** Parameterize, no
   exceptions.
5. **Do not edit a test to make it green**, unless the task is
   specifically to update the test's expectations. A red test is
   information, not an obstacle.
6. **Do not leave process references in source** — no story numbers,
   epic IDs, or planning notes in comments. Comments explain *why*, not
   *which ticket this belongs to*.

## With the repository

7. **Do not run destructive commands without asking first**:
   `git reset --hard`, `git checkout -- .`, `rm -rf` inside the repo,
   `git push --force`.
8. **Do not resolve end-of-wave merge conflicts yourself.** A conflict
   means two stories touched the same area, which means scope
   declarations are wrong — the fix belongs in story splitting, not in
   this merge.

## With the process

9. **The code author does not review their own code.** The reviewer must
   be a separate session with a clean context.
10. **Do not skip gates.** Do not declare a story done without sufficient
    evidence; do not advance to the next phase when the previous gate has
    not been approved.
11. **Do not modify source files of external references.** BMAD
    customizations go in `_bmad/custom/`, not in `customize.toml` of the
    upstream repo — the next upgrade would overwrite them.
12. **Do not fabricate metrics, API names, or library behavior.** If
    unsure, look it up; if you cannot find it, record it as an
    assumption.
