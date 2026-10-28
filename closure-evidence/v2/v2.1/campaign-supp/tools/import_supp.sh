#!/bin/zsh
# import_supp.sh C: after the supplementary campaign finishes (C/campaign.done present, no worker alive), keep each
# worker's record and log byte-for-byte under closure-evidence/v2/v2.1/mutation-workers/ as sw-w<N>, through the record
# tool's own --import (it refuses to replace a history); then mirror the campaign dir (minus the worker worktrees and
# env dirs) into campaign-supp/results/. Run from the repository root (the v21 worktree). Nothing is committed here.
# Adapted from campaign-9 import9.sh: 2 workers named w0/w1.
set -u
C=${1:?campaign dir}; W=$(git rev-parse --show-toplevel) || exit 9
[[ -e $C/campaign.done ]] || { echo "refused: $C/campaign.done absent (campaign not finished)"; exit 2; }
(( $(pgrep -f 'validation/v2/mutation.py run' | wc -l) == 0 )) || { echo "refused: a mutation.py run process is alive"; exit 2; }
for N in w0 w1; do
  wt=$C/$N; [[ -d $wt && -e $C/$N.finished ]] || { echo "refused: worker $N has no worktree or no .finished"; exit 2; }
  st=$(tr -d '\n' < $C/$N.status-after); [[ -n $st ]] && st="dirty: $st" || st="clean"
  desc="finished $(cat $C/$N.finished); git status --porcelain after: $st (supplementary campaign, snapshot $(cut -c1-7 $C/$N.snapshot))"
  /opt/homebrew/bin/python3 -P -B validation/qualification/v21_mutation_record.py --import sw-$N $wt "$desc" $C/$N.log || exit 3
done
R=$W/closure-evidence/v2/v2.1/campaign-supp/results; mkdir -p $R
rsync -a --exclude '/w[0-9]/' --exclude '/w[0-9].env/' $C/ $R/ || exit 4
echo "imported 2 workers; results mirrored to $R ($(ls $R | wc -l | tr -d ' ') entries); records: $(ls $W/closure-evidence/v2/v2.1/mutation-workers/sw-w* 2>/dev/null | wc -l | tr -d ' ') files"
