#!/bin/zsh
# worker.sh NAME SNAP: one V2.1 mutation worker (owner B-03b) in $SP/m21/NAME — a detached worktree at commit SNAP,
# targets from $SP/m21/NAME.targets. Hermetic: env -i; PATH without any directory holding an executable `opencode`;
# HOME, XDG_CONFIG/DATA/STATE/CACHE and TMPDIR in the worker's own $SP/m21/NAME.env (no two workers share a scratch
# directory, and mutation.py's copies land in that TMPDIR); the run wrapped by validation/v2/owned_run.py, which
# records the processes before, at exit and after (escaped / orphans). No real client, provider, credential or
# operator data is reachable: the guard PATH has no client, and every client/provider in the kill tests is a fake.
SP=/private/tmp/claude-501/-Users-nghinh-Downloads-projects-ai-sdlc/845c9f11-719f-4f92-a0ed-4f4a07d6e27b/scratchpad
W=/Users/nghinh/Downloads/projects/ai-sdlc/.claude/worktrees/v21
D=$SP/m21; N=$1; SNAP=$2
[[ -n $N && -n $SNAP && -s $D/$N.targets && ! -e $D/$N ]] || { echo "usage: worker.sh NAME SNAP (targets present, worktree absent)"; exit 2; }
GUARD_PATH=$(print -rl -- ${(s.:.)PATH} | while read -r d; do [[ -x $d/opencode ]] || print -r -- $d; done | paste -sd: -)
E=$D/$N.env; mkdir -p $E/home $E/xdg/config $E/xdg/data $E/xdg/state $E/xdg/cache $E/tmp
git -C $W worktree add -q --detach $D/$N $SNAP || exit 1
R=$D/$N/closure-evidence/v2/v2.1/MUTATION.json; [[ -e $R ]] && mv $R $R.committed-at-snapshot
HENV=(env -i PATH=$GUARD_PATH HOME=$E/home XDG_CONFIG_HOME=$E/xdg/config XDG_DATA_HOME=$E/xdg/data XDG_STATE_HOME=$E/xdg/state
      XDG_CACHE_HOME=$E/xdg/cache TMPDIR=$E/tmp LANG=en_US.UTF-8 USER=$USER LOGNAME=$LOGNAME)
print -r -- "HENV=(${(q)HENV[@]})" > $E/env.sh
git -C $D/$N rev-parse HEAD > $D/$N.snapshot
date -u +%FT%TZ > $D/$N.started
(cd $D/$N && $HENV /opt/homebrew/bin/python3 -P validation/v2/owned_run.py --out $D/$N.owned.json -- \
   /opt/homebrew/bin/python3 -P validation/v2/mutation.py run $(cat $D/$N.targets) > $D/$N.log 2>&1; echo "exit $?" >> $D/$N.log)
date -u +%FT%TZ > $D/$N.finished
git -C $D/$N status --porcelain --untracked-files=no > $D/$N.status-after
