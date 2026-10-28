#!/bin/zsh
# sync.sh C DEST: every 600 s, mirror the scratch campaign dir C (queue, claims, each worker's log / record / marks,
# owned_run outputs, progress and disk logs) to DEST on the persistent disk — so the scratchpad is never the only
# holder of a checkpoint (macOS clears /tmp). The workers' detached worktrees (w<N>/) and their env dirs are left out
# (regenerable from the snapshot). Mirror only: nothing is deleted on either side. One last pass after C/campaign.done,
# then exits.
C=$1; D=$2
[[ -d $C && -n $D ]] || { echo "usage: sync.sh C DEST"; exit 2; }
mkdir -p $D
while :; do
  rsync -a --exclude '/w[0-9]/' --exclude '/w[0-9][0-9]/' --exclude '/w[0-9].env/' --exclude '/w[0-9][0-9].env/' \
        "$C/" "$D/" 2>> $D/sync.err && echo "$(date -u +%FT%TZ) synced" >> $D/sync.log
  [[ -e $C/campaign.done ]] && break
  sleep 600
done
echo "$(date -u +%FT%TZ) final pass done" >> $D/sync.log
