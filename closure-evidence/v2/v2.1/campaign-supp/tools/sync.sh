#!/bin/zsh
# sync.sh C DEST: every 600 s, mirror the scratch campaign dir C (queue, claims, each worker's log / record / marks,
# owned_run outputs, progress and disk logs) to DEST on the persistent disk — so the scratchpad is never the only
# holder of a checkpoint (macOS clears /tmp). The workers' detached worktrees (w<N>/) and their env dirs are left out
# (regenerable from the snapshot). Mirror only: nothing is deleted on either side. One last pass after C/campaign.done,
# then exits.
C=$1; D=$2
[[ -d $C && -n $D ]] || { echo "usage: sync.sh C DEST"; exit 2; }
setopt null_glob   # a worker-glob with no match expands to nothing instead of aborting
mkdir -p $D
while :; do
  rsync -a --exclude '/w[0-9]/' --exclude '/w[0-9][0-9]/' --exclude '/w[0-9].env/' --exclude '/w[0-9][0-9].env/' \
        "$C/" "$D/" 2>> $D/sync.err && echo "$(date -u +%FT%TZ) synced" >> $D/sync.log
  # the per-target records live INSIDE the excluded worktrees; mirror just those small JSONs (not the 1.9G tree)
  # so a completed target is durably recoverable from DEST. rsync temp+rename ⇒ DEST file never partial.
  for w in $C/w[0-9] $C/w[0-9][0-9]; do
    rd="$w/closure-evidence/v2/v2.1"; [[ -d $rd ]] || continue
    b=$(basename $w); mkdir -p "$D/records/$b"
    rsync -a --include='MUTATION*.json' --exclude='*' "$rd/" "$D/records/$b/" 2>>$D/sync.err
  done
  [[ -e $C/campaign.done ]] && break
  sleep 600
done
echo "$(date -u +%FT%TZ) final pass done" >> $D/sync.log
