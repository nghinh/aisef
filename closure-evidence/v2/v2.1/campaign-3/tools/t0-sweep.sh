#!/bin/zsh
# t0-sweep.sh SHA OUT: the T0 sweep (sweep.py) at a detached checkout of SHA, under the workers' environment (env -i, PATH
# without opencode, scratch HOME/XDG/TMPDIR under OUT), under the machine-wide heavy lock. Results outside the tree.
SP=/private/tmp/claude-501/-Users-nghinh-Downloads-projects-ai-sdlc/845c9f11-719f-4f92-a0ed-4f4a07d6e27b/scratchpad
W=/Users/nghinh/Downloads/projects/ai-sdlc/.claude/worktrees/v21
SHA=$1; OUT=$2
[[ -n $SHA && -n $OUT && ! -e $OUT ]] || { echo "usage: t0-sweep.sh SHA OUT (OUT absent)"; exit 2; }
mkdir -p $OUT/home $OUT/xdg/{config,data,state,cache} $OUT/tmp
GP=$(print -rl -- ${(s.:.)PATH} | while read -r d; do [[ -x $d/opencode ]] || print -r -- $d; done | paste -sd: -)
git -C $W worktree add -q --detach $OUT/rc $SHA || exit 1
cd $OUT/rc || exit 9
echo "HEAD $(git rev-parse HEAD) dirty: [$(git status --porcelain | tr '\n' ' ')] free $(df -g /System/Volumes/Data | awk 'NR==2{print $4}') GiB" > $OUT/sweep.log
echo "=== sweep $(date '+%F %T')" >> $OUT/sweep.log
zsh $SP/heavy.sh t0-sweep env -i PATH=$GP HOME=$OUT/home XDG_CONFIG_HOME=$OUT/xdg/config XDG_DATA_HOME=$OUT/xdg/data \
    XDG_STATE_HOME=$OUT/xdg/state XDG_CACHE_HOME=$OUT/xdg/cache TMPDIR=$OUT/tmp LANG=en_US.UTF-8 USER=$USER LOGNAME=$LOGNAME \
    /opt/homebrew/bin/python3 -P closure-evidence/v2/v2.1/campaign-3/tools/sweep.py $OUT/sweep.jsonl >> $OUT/sweep.log 2>&1
echo "sweep RC $?" >> $OUT/sweep.log
echo "HEAD after $(git rev-parse HEAD) dirty: [$(git status --porcelain | tr '\n' ' ')]" >> $OUT/sweep.log
echo "=== DONE $(date '+%F %T')" >> $OUT/sweep.log
echo done > $OUT/sweep.done
