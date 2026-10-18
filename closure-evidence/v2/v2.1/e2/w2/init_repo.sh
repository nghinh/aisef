#!/bin/zsh
# E2 / W2 (brownfield): reproduce the baseline repository, bit for bit, as one commit.
#
#   zsh init_repo.sh <new directory>            (refuses an existing one)
#
# Source: the hand-written project `bread` (~/Downloads/projects/bread, author Nghi Nguyen, Aug–Oct 2026; never developed
# by AISEF — no .aisef/, no AISEF-managed .opencode/, no closure-evidence/) at commit 6fde318ecac1e447f49d6b642707c78f17ddcb63,
# filtered to its evidence-discipline linter (five tracked files, taken with `git archive`, so the bytes are the commit's).
# Added by the W2 lane, from this directory's baseline/: docs/requirements-delta.md (the public task), README.md, .gitignore.
# The commit is deterministic (fixed author, committer, dates and message), so every reproduction yields the same sha —
# the harness's source_identity (validation/experiments/harness.py) then binds the same commit, tree and files digest.
set -eu
D=${0:A:h}
SRC=${W2_SOURCE_REPO:-$HOME/Downloads/projects/bread}
SRC_COMMIT=6fde318ecac1e447f49d6b642707c78f17ddcb63
OUT=${1:?usage: zsh init_repo.sh <new directory>}
[[ ! -e $OUT ]] || { echo "refused: $OUT exists — the baseline is reproduced into a new directory" >&2; exit 2; }
git -C "$SRC" cat-file -e "$SRC_COMMIT^{commit}" || { echo "refused: $SRC does not hold $SRC_COMMIT" >&2; exit 2; }
mkdir -p "$OUT"
git -C "$SRC" archive --format=tar "$SRC_COMMIT" -- \
    infrastructure/__init__.py infrastructure/ci/__init__.py infrastructure/ci/evidence_discipline.py \
    infrastructure/ci/test_evidence_discipline.py infrastructure/ci/run_registry.json | tar -x -C "$OUT"
mkdir -p "$OUT/docs"
cp "$D/baseline/docs/requirements-delta.md" "$OUT/docs/requirements-delta.md"
cp "$D/baseline/README.md" "$OUT/README.md"
cp "$D/baseline/.gitignore" "$OUT/.gitignore"
chmod 644 "$OUT"/.gitignore "$OUT"/README.md "$OUT"/docs/requirements-delta.md "$OUT"/infrastructure/__init__.py \
    "$OUT"/infrastructure/ci/*.py "$OUT"/infrastructure/ci/*.json
export GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null
export GIT_AUTHOR_NAME="bread maintainers (filtered by the AISEF E2 W2 lane)" GIT_AUTHOR_EMAIL="e2-w2@aisef.invalid"
export GIT_COMMITTER_NAME="$GIT_AUTHOR_NAME" GIT_COMMITTER_EMAIL="$GIT_AUTHOR_EMAIL"
export GIT_AUTHOR_DATE="2026-10-18T06:00:00+00:00" GIT_COMMITTER_DATE="2026-10-18T06:00:00+00:00"
git -C "$OUT" -c init.defaultBranch=main -c core.autocrlf=false -c core.filemode=true init -q
git -C "$OUT" -c core.autocrlf=false add -A
git -C "$OUT" -c core.autocrlf=false -c commit.gpgsign=false commit -q -F - <<'EOF'
W2 baseline: the evidence-discipline linter of bread@6fde318 plus docs/requirements-delta.md

Five files of ~/Downloads/projects/bread at 6fde318ecac1e447f49d6b642707c78f17ddcb63 (git archive):
infrastructure/__init__.py, infrastructure/ci/__init__.py, infrastructure/ci/evidence_discipline.py,
infrastructure/ci/test_evidence_discipline.py, infrastructure/ci/run_registry.json. Added for the
experiment: docs/requirements-delta.md (the public task), README.md, .gitignore.
EOF
echo "baseline $(git -C "$OUT" rev-parse HEAD) tree $(git -C "$OUT" rev-parse 'HEAD^{tree}') at $OUT"
