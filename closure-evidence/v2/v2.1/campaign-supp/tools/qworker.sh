#!/bin/zsh
# qworker.sh C NAME SNAP: one supplementary-campaign worker pulling targets from the shared queue $C/queue.txt (one
# target per line, largest mutant-estimate first). A target is taken by an atomic mkdir of $C/claims/<line number>; the
# worker runs `mutation.py run TARGET` for it in its OWN detached worktree at SNAP ($C/NAME), hermetic: env -i, PATH
# with every directory that holds an `opencode` executable removed, its own HOME/XDG/TMPDIR, each run inside
# owned_run.py (no provider call). Between targets — the only checkpoint, so nothing in progress is ever cut — it stops
# when $C/STOP exists or the disk has < 10 GiB free (the graceful tier; the watchdog holds the 6 GiB hard floor).
# Every run's output is appended to $C/NAME.log; the worker's record is copied to $C/NAME.record.json after each target.
# Reused verbatim from campaign-9's proven qworker (which ran 10/10 clean), minus the --order table (never used for V2.1).
W=${QW_REPO:-/Users/nghinh/Downloads/projects/ai-sdlc/.claude/worktrees/v21}
C=$1; N=$2; SNAP=$3
[[ -n $C && -n $N && -n $SNAP && -s $C/queue.txt && ! -e $C/$N ]] || { echo "usage: qworker.sh C NAME SNAP (queue present, worktree absent)"; exit 2; }
GUARD_PATH=$(print -rl -- ${(s.:.)PATH} | while read -r d; do [[ -x $d/opencode ]] || print -r -- $d; done | paste -sd: -)
E=$C/$N.env; mkdir -p $E/home $E/xdg/config $E/xdg/data $E/xdg/state $E/xdg/cache $E/tmp $C/claims $C/owned
git -C $W worktree add -q --detach $C/$N $SNAP || exit 1
R=$C/$N/closure-evidence/v2/v2.1/MUTATION.json; [[ -e $R ]] && mv $R $R.committed-at-snapshot
HENV=(env -i PATH=$GUARD_PATH HOME=$E/home XDG_CONFIG_HOME=$E/xdg/config XDG_DATA_HOME=$E/xdg/data XDG_STATE_HOME=$E/xdg/state
      XDG_CACHE_HOME=$E/xdg/cache TMPDIR=$E/tmp LANG=en_US.UTF-8 USER=$USER LOGNAME=$LOGNAME)
git -C $C/$N rev-parse HEAD > $C/$N.snapshot
date -u +%FT%TZ > $C/$N.started
i=0
while IFS= read -r t; do
  i=$((i+1))
  [[ -e $C/STOP ]] && { echo "$(date -u +%FT%TZ) STOP file: stopping before claiming line $i" >> $C/$N.log; break; }
  free=$(df -g /System/Volumes/Data | awk 'NR==2{print $4}')
  (( free >= 10 )) || { echo "$(date -u +%FT%TZ) DISK $free GiB free (< 10): stopping before claiming line $i" >> $C/$N.log; break; }
  mkdir $C/claims/$i 2>/dev/null || continue
  echo "$N $t $(date -u +%FT%TZ)" > $C/claims/$i/by
  echo "=== $(date -u +%FT%TZ) $N line $i $t (free $free GiB)" >> $C/$N.log
  (cd $C/$N && $HENV /opt/homebrew/bin/python3 -P validation/v2/owned_run.py --out $C/owned/$N-$i.json -- \
     /opt/homebrew/bin/python3 -P validation/v2/mutation.py run $t >> $C/$N.log 2>&1)
  rc=$?; echo "exit $rc line $i" >> $C/$N.log
  [[ -e $R ]] && cp $R $C/$N.record.json
  echo "$(date -u +%FT%TZ) exit $rc" > $C/claims/$i/done
  (( rc == 3 )) && { echo "$(date -u +%FT%TZ) runner STOPPED (exit 3): this worker stops" >> $C/$N.log; break; }
done < $C/queue.txt
date -u +%FT%TZ > $C/$N.finished
git -C $C/$N status --porcelain --untracked-files=no > $C/$N.status-after
