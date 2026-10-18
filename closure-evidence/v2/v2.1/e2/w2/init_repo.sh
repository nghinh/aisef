#!/bin/zsh
# E2 / W2 (brownfield): reproduce the baseline repository, bit for bit, as one commit — from this directory alone.
#
#   zsh init_repo.sh <new directory>            (refuses an existing one, and a digest that does not match)
#
# History (provenance, PROVENANCE.json): the five product files are the project `bread` (~/Downloads/projects/bread) at
# commit 6fde318ecac1e447f49d6b642707c78f17ddcb63, filtered to its evidence-discipline linter with `git archive` on
# 2026-10-18 (the lane's first version of this script read bread directly). bread was not produced by AISEF (0 commits
# mention aisef; 300/300 lines of the linter blamed to Nghi Nguyen; no .aisef/, no .opencode/, no closure-evidence/);
# bread itself is developed with coding agents (11/418 commits authored "Claude Fable 5", .claude/ and AGENTS.md present).
# Since lane W2-2 the archived bytes are committed under baseline/source/ with their sha256 below, so the baseline is
# reproducible from this evidence alone: bread is no longer read, and a copy whose digest differs is refused.
# Added by the W2 lane, from baseline/: docs/requirements-delta.md (the public task), README.md, .gitignore.
# The commit is deterministic (fixed author, committer, dates and message), so every reproduction yields the same sha —
# the harness's source_identity (validation/experiments/harness.py) then binds the same commit, tree and files digest.
set -eu
D=${0:A:h}
OUT=${1:?usage: zsh init_repo.sh <new directory>}
[[ ! -e $OUT ]] || { echo "refused: $OUT exists — the baseline is reproduced into a new directory" >&2; exit 2; }
# the five files of bread@6fde318 as committed under baseline/source/ (sha256 of the archived bytes)
( cd "$D/baseline/source" && shasum -a 256 -c --status <<'EOF' ) || { echo "refused: a file under baseline/source/ does not match its recorded sha256" >&2; exit 2; }
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  infrastructure/__init__.py
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  infrastructure/ci/__init__.py
048af01c3a1b040fbd99cf89a1711a96db2ba400a62b792f27486331d356dc9b  infrastructure/ci/evidence_discipline.py
e19514d3c87ea42e696de1bd8fdecb555566d2b8b0409db85f37a14b9f1fb983  infrastructure/ci/test_evidence_discipline.py
da2cdc40dc7f841e21c6e5cbdd012c8125bb370855659b8cb5a5552ec7c0bba8  infrastructure/ci/run_registry.json
EOF
mkdir -p "$OUT/infrastructure/ci" "$OUT/docs"
for f in infrastructure/__init__.py infrastructure/ci/__init__.py infrastructure/ci/evidence_discipline.py \
         infrastructure/ci/test_evidence_discipline.py infrastructure/ci/run_registry.json; do
    cp "$D/baseline/source/$f" "$OUT/$f"
done
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
