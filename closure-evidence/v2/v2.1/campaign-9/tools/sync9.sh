#!/bin/zsh
# sync9.sh C DEST: every 600 s, mirror the campaign directory C (the queue, claims, each worker's log / record / marks,
# owned_run outputs, progress and disk logs) to DEST on the persistent disk, so the scratchpad is never the only
# holder of a checkpoint; the workers' detached worktrees (c3-w<N>/) and their env directories are left out (they
# are regenerable from the snapshot). Mirrors only: nothing is deleted on either side. One last pass after
# C/campaign.done appears, then exits.
C=$1; D=$2
[[ -d $C && -n $D ]] || { echo "usage: sync9.sh C DEST"; exit 2; }
mkdir -p $D
while :; do
  rsync -a --exclude '/c3-w[0-9]/' --exclude '/c3-w[0-9][0-9]/' --exclude '/c3-w[0-9].env/' --exclude '/c3-w[0-9][0-9].env/' \
        "$C/" "$D/" 2>> $D/sync.err && echo "$(date -u +%FT%TZ) synced" >> $D/sync.log
  [[ -e $C/campaign.done ]] && break
  sleep 600
done
echo "$(date -u +%FT%TZ) final pass done" >> $D/sync.log
