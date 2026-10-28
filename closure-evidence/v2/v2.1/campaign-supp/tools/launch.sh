#!/bin/zsh
# launch.sh C D SNAP: start the supplementary campaign — 2 workers (w0, w1) + watchdog + disk-sync, all detached.
#   C    scratch campaign dir (queue, claims, worker worktrees w<N>/, env, logs, records)
#   D    durable mirror dir on the persistent disk (closure-evidence/.../campaign-supp/run) — sync.sh keeps it current
#   SNAP the pinned merged head to measure (product == fce3d7b7, plus the two kill-test edits)
# Refuses to start beside another `mutation.py run`. Nothing here deletes anything.
set -u
TOOLS=${0:A:h}
C=$1; D=$2; SNAP=$3
mkdir -p $C
pgrep -f 'validation/v2/mutation.py run' >/dev/null && { echo "refused: a mutation.py run is already alive"; exit 2; }
[[ -e $C/campaign.started ]] && { echo "refused: $C already started"; exit 2; }
/opt/homebrew/bin/python3 -P $TOOLS/make_queue.py $C || exit 3
cp $TOOLS/progress.py $C/progress.py
date -u +%FT%TZ > $C/campaign.started
nohup zsh $TOOLS/watchdog.sh $C >> $C/watchdog.out 2>&1 & echo "watchdog $!" >> $C/launch.log
nohup zsh $TOOLS/sync.sh $C $D   >> $C/sync.out     2>&1 & echo "sync $!"     >> $C/launch.log
for N in w0 w1; do
  nohup zsh $TOOLS/qworker.sh $C $N $SNAP >> $C/$N.out 2>&1 & echo "worker $N $!" >> $C/launch.log
  sleep 2   # stagger the two `git worktree add` calls off the shared index
done
echo "launched $(date -u +%FT%TZ): C=$C D=$D SNAP=$SNAP" >> $C/launch.log
cat $C/launch.log
