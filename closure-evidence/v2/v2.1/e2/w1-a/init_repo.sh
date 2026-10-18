#!/bin/sh
# W1-a baseline: a clean git repository with ONE commit of baseline/ in the directory given.
#   sh init_repo.sh /path/to/new/dir        (the directory must not exist, or be empty)
# The commit is reproducible: fixed author, committer and dates, so every repository this creates has the same
# commit sha — the one the sealed bundles name as their baseline (arms/bundle.json, evaluator/bundle.json).
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
DEST=${1:?usage: init_repo.sh DEST}
if [ -e "$DEST" ] && [ -n "$(ls -A "$DEST" 2>/dev/null)" ]; then
    echo "init_repo.sh: $DEST exists and is not empty" >&2
    exit 2
fi
mkdir -p "$DEST"
# copy the tree, every file mode 0644 (a tar of modes would make the commit depend on the checkout's umask)
(cd "$HERE/baseline" && find . -type f | sort) | while IFS= read -r f; do
    mkdir -p "$DEST/$(dirname "$f")"
    cp "$HERE/baseline/$f" "$DEST/$f"
    chmod 0644 "$DEST/$f"
done
export GIT_AUTHOR_NAME="treesum baseline" GIT_AUTHOR_EMAIL="baseline@treesum.invalid"
export GIT_COMMITTER_NAME="treesum baseline" GIT_COMMITTER_EMAIL="baseline@treesum.invalid"
export GIT_AUTHOR_DATE="2026-10-18T00:00:00+0000" GIT_COMMITTER_DATE="2026-10-18T00:00:00+0000"
export GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null
git -C "$DEST" init -q -b main
git -C "$DEST" -c core.autocrlf=false -c core.filemode=false add -A
git -C "$DEST" -c core.autocrlf=false -c core.filemode=false -c commit.gpgsign=false \
    commit -q --no-verify -m "treesum: baseline (public task text, empty package, smoke test)"
git -C "$DEST" rev-parse HEAD
