#!/bin/zsh
# run-readset.sh SHA OUT: the read-set recorder (validation/v21/read_set.py) at a detached, clean checkout of SHA, under
# the workers' environment (env -i, PATH without opencode, scratch HOME/XDG/TMPDIR under OUT) and the machine-wide
# heavy lock. The record is OUT/read-set.json; its exit status and the checkout's state before/after are in OUT/run.log.
SP=/private/tmp/claude-501/-Users-nghinh-Downloads-projects-ai-sdlc/845c9f11-719f-4f92-a0ed-4f4a07d6e27b/scratchpad
W=/Users/nghinh/Downloads/projects/ai-sdlc/.claude/worktrees/v21
SHA=$1; OUT=$2
[[ -n $SHA && -n $OUT && ! -e $OUT ]] || { echo "usage: run-readset.sh SHA OUT (OUT absent)"; exit 2; }
mkdir -p $OUT/home $OUT/xdg/{config,data,state,cache} $OUT/tmp
GP=$(print -rl -- ${(s.:.)PATH} | while read -r d; do [[ -x $d/opencode ]] || print -r -- $d; done | paste -sd: -)
git -C $W worktree add -q --detach $OUT/rc $SHA || exit 1
cd $OUT/rc || exit 9
echo "HEAD $(git rev-parse HEAD) dirty: [$(git status --porcelain | tr '\n' ' ')] free $(df -g /System/Volumes/Data | awk 'NR==2{print $4}') GiB" > $OUT/run.log
echo "=== read-set $(date '+%F %T')" >> $OUT/run.log
zsh $SP/heavy.sh read-set env -i PATH=$GP HOME=$OUT/home XDG_CONFIG_HOME=$OUT/xdg/config XDG_DATA_HOME=$OUT/xdg/data \
    XDG_STATE_HOME=$OUT/xdg/state XDG_CACHE_HOME=$OUT/xdg/cache TMPDIR=$OUT/tmp LANG=en_US.UTF-8 USER=$USER LOGNAME=$LOGNAME \
    /opt/homebrew/bin/python3 -P validation/v21/read_set.py --out $OUT/read-set.json --commit $SHA >> $OUT/run.log 2>&1
echo "read-set RC $?" >> $OUT/run.log
echo "HEAD after $(git rev-parse HEAD) dirty: [$(git status --porcelain | tr '\n' ' ')]" >> $OUT/run.log
echo "=== DONE $(date '+%F %T')" >> $OUT/run.log
echo done > $OUT/read-set.done
