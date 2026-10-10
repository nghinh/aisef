#!/bin/zsh
# check_at_snapshot.sh: the runner's own verdict on campaign 2's merged record, in a fresh detached worktree at the
# snapshot (the record is copied in, nothing committed), env -i with PATH without opencode and scratch HOME/XDG/TMPDIR.
set -u
SP=/private/tmp/claude-501/-Users-nghinh-Downloads-projects-ai-sdlc/845c9f11-719f-4f92-a0ed-4f4a07d6e27b/scratchpad
R=/Users/nghinh/Downloads/projects/ai-sdlc/.claude/worktrees/v21
OUT=$SP/m21/account; T=$SP/m21/check-tree; E=$SP/m21/check-env
[[ -e $OUT/MUTATION.json ]] || { echo "no merged record at $OUT"; exit 2; }
[[ -e $T ]] || git -C $R worktree add --detach $T 5719f1f87ebbb2d3f19a3f0629ee656c93597c23 >/dev/null 2>&1 || exit 2
[[ $(git -C $T rev-parse HEAD) == 5719f1f87ebbb2d3f19a3f0629ee656c93597c23 ]] || { echo "check tree not at the snapshot"; exit 2; }
cp $OUT/MUTATION.json $T/closure-evidence/v2/v2.1/MUTATION.json
mkdir -p $E/home $E/tmp $E/xdg/{config,data,state,cache}
GP=$(print -rl -- ${(s.:.)PATH} | while read -r d; do [[ -x $d/opencode ]] || print -r -- $d; done | paste -sd: -)
cd $T && env -i PATH=$GP HOME=$E/home TMPDIR=$E/tmp XDG_CONFIG_HOME=$E/xdg/config XDG_DATA_HOME=$E/xdg/data \
  XDG_STATE_HOME=$E/xdg/state XDG_CACHE_HOME=$E/xdg/cache /opt/homebrew/bin/python3 -P -B validation/v2/mutation.py --check \
  > $OUT/check.out 2>&1; rc=$?
echo "exit $rc" >> $OUT/check.out
git -C $T status --porcelain > $OUT/check-tree-status.txt
echo "check exit $rc; $(grep -c . $OUT/check.out) lines; tree status lines $(grep -c . $OUT/check-tree-status.txt)"
