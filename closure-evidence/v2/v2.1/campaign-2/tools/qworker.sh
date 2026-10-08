#!/bin/zsh
# qworker.sh C NAME SNAP [TABLE]: one campaign-2 worker pulling targets from the shared queue $C/queue.txt (one target
# per line, longest expected first). A target is taken by an atomic mkdir of $C/claims/<line number>; the worker runs
# `mutation.py run [--order TABLE] TARGET` for it in its own detached worktree at SNAP ($C/NAME), hermetic like
# worker.sh (env -i, PATH without opencode, own HOME/XDG/TMPDIR), each run inside owned_run.py. Between targets — the
# only checkpoint, so nothing in progress is ever cut — it stops when $C/STOP exists or the disk has < 10 GiB free.
# Every run's output is appended to $C/NAME.log; the worker's record is copied to $C/NAME.record.json after each target.
SP=/private/tmp/claude-501/-Users-nghinh-Downloads-projects-ai-sdlc/845c9f11-719f-4f92-a0ed-4f4a07d6e27b/scratchpad
W=${QW_REPO:-/Users/nghinh/Downloads/projects/ai-sdlc/.claude/worktrees/v21}   # QW_REPO: the self-test's toy repo
C=$1; N=$2; SNAP=$3; TABLE=$4
[[ -n $C && -n $N && -n $SNAP && -s $C/queue.txt && ! -e $C/$N ]] || { echo "usage: qworker.sh C NAME SNAP [TABLE] (queue present, worktree absent)"; exit 2; }
GUARD_PATH=$(print -rl -- ${(s.:.)PATH} | while read -r d; do [[ -x $d/opencode ]] || print -r -- $d; done | paste -sd: -)
E=$C/$N.env; mkdir -p $E/home $E/xdg/config $E/xdg/data $E/xdg/state $E/xdg/cache $E/tmp $C/claims $C/owned
git -C $W worktree add -q --detach $C/$N $SNAP || exit 1
R=$C/$N/closure-evidence/v2/v2.1/MUTATION.json; [[ -e $R ]] && mv $R $R.committed-at-snapshot
HENV=(env -i PATH=$GUARD_PATH HOME=$E/home XDG_CONFIG_HOME=$E/xdg/config XDG_DATA_HOME=$E/xdg/data XDG_STATE_HOME=$E/xdg/state
      XDG_CACHE_HOME=$E/xdg/cache TMPDIR=$E/tmp LANG=en_US.UTF-8 USER=$USER LOGNAME=$LOGNAME)
ORD=(); [[ -n $TABLE ]] && ORD=(--order $TABLE)
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
     /opt/homebrew/bin/python3 -P validation/v2/mutation.py run $ORD $t >> $C/$N.log 2>&1)
  rc=$?; echo "exit $rc line $i" >> $C/$N.log
  [[ -e $R ]] && cp $R $C/$N.record.json
  echo "$(date -u +%FT%TZ) exit $rc" > $C/claims/$i/done
  # exit 3: the runner stopped (an ownership failure, or an earlier run's leftovers): never run beside it
  (( rc == 3 )) && { echo "$(date -u +%FT%TZ) runner STOPPED (exit 3): this worker stops" >> $C/$N.log; break; }
done < $C/queue.txt
date -u +%FT%TZ > $C/$N.finished
git -C $C/$N status --porcelain --untracked-files=no > $C/$N.status-after
