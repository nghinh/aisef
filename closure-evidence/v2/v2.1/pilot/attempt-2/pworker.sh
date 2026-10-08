#!/bin/zsh
# pworker.sh NAME SNAP MODE [TABLE]: one pilot run (owner 2026-10-07 step 7) — worker.sh's hermetic setup (env -i, PATH
# without opencode, own HOME/XDG/TMPDIR, owned_run.py around the run) in $P/NAME, a detached worktree at SNAP, targets
# from $P/NAME.targets; MODE decl = `mutation.py run TARGETS` (declared kill-set order), MODE ord = `run --order TABLE
# TARGETS` (TABLE: the committed execution-order table, a path inside the snapshot).
SP=/private/tmp/claude-501/-Users-nghinh-Downloads-projects-ai-sdlc/845c9f11-719f-4f92-a0ed-4f4a07d6e27b/scratchpad
W=/Users/nghinh/Downloads/projects/ai-sdlc/.claude/worktrees/v21
P=$SP/m21/pilot; N=$1; SNAP=$2; MODE=$3; TABLE=$4
[[ -n $N && -n $SNAP && -s $P/$N.targets && ! -e $P/$N && ( $MODE == decl || ( $MODE == ord && -n $TABLE ) ) ]] || { echo "usage: pworker.sh NAME SNAP decl|ord [TABLE]"; exit 2; }
FREE=$(df -g /System/Volumes/Data | awk 'NR==2{print $4}')
(( FREE >= 10 )) || { echo "REFUSED $N: $FREE GiB free, 10 needed" | tee $P/$N.refused; exit 4; }
GUARD_PATH=$(print -rl -- ${(s.:.)PATH} | while read -r d; do [[ -x $d/opencode ]] || print -r -- $d; done | paste -sd: -)
E=$P/$N.env; mkdir -p $E/home $E/xdg/config $E/xdg/data $E/xdg/state $E/xdg/cache $E/tmp
git -C $W worktree add -q --detach $P/$N $SNAP || exit 1
R=$P/$N/closure-evidence/v2/v2.1/MUTATION.json; [[ -e $R ]] && mv $R $R.committed-at-snapshot
HENV=(env -i PATH=$GUARD_PATH HOME=$E/home XDG_CONFIG_HOME=$E/xdg/config XDG_DATA_HOME=$E/xdg/data XDG_STATE_HOME=$E/xdg/state
      XDG_CACHE_HOME=$E/xdg/cache TMPDIR=$E/tmp LANG=en_US.UTF-8 USER=$USER LOGNAME=$LOGNAME)
ORD=(); [[ $MODE == ord ]] && ORD=(--order $TABLE)
git -C $P/$N rev-parse HEAD > $P/$N.snapshot
date -u +%FT%TZ > $P/$N.started
(cd $P/$N && $HENV /opt/homebrew/bin/python3 -P validation/v2/owned_run.py --out $P/$N.owned.json -- \
   /opt/homebrew/bin/python3 -P validation/v2/mutation.py run $ORD $(cat $P/$N.targets) > $P/$N.log 2>&1; echo "exit $?" >> $P/$N.log)
date -u +%FT%TZ > $P/$N.finished
cp $R $P/$N.record.json 2>/dev/null
git -C $P/$N status --porcelain --untracked-files=no > $P/$N.status-after
