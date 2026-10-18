#!/bin/zsh
# import9.sh C: after campaign 9 finished (C/campaign.done present, no worker alive), keep each worker's record and log
# byte for byte under closure-evidence/v2/v2.1/mutation-workers/ as c9-w<N> (the campaign script names the directories
# c3-w<N>; campaign 8 did the same rename), through the record tool's own --import (it refuses to replace a history);
# then mirror the campaign directory (minus the worker worktrees and env dirs) into campaign-9/results/ with the worker
# files renamed c9-w*. Run from the repository root (the v21 worktree). Nothing is committed here.
set -u
C=${1:?campaign dir}; W=$(git rev-parse --show-toplevel) || exit 9
[[ -e $C/campaign.done ]] || { echo "refused: $C/campaign.done absent (campaign not finished)"; exit 2; }
(( $(pgrep -f 'validation/v2/mutation.py run' | wc -l) == 0 )) || { echo "refused: a mutation.py run process is alive"; exit 2; }
for i in 1 2 3 4; do
  wt=$C/c3-w$i; [[ -d $wt && -e $C/c3-w$i.finished ]] || { echo "refused: worker c3-w$i has no worktree or no .finished"; exit 2; }
  st=$(tr -d '\n' < $C/c3-w$i.status-after); [[ -n $st ]] && st="dirty: $st" || st="clean"
  status="finished $(cat $C/c3-w$i.finished); git status --porcelain after: $st (campaign 9, snapshot $(cut -c1-7 $C/c3-w$i.snapshot); the worker directory is named c3-w$i by the campaign script)"
  /opt/homebrew/bin/python3 -P -B validation/qualification/v21_mutation_record.py --import c9-w$i $wt "$status" $C/c3-w$i.log || exit 3
done
R=$W/closure-evidence/v2/v2.1/campaign-9/results; mkdir -p $R
rsync -a --exclude '/c3-w[0-9]/' --exclude '/c3-w[0-9].env/' --exclude '/c3-w[0-9].record.json' --exclude '/c3-w[0-9].log' \
      --exclude '/sync.log' --exclude '/sync.err' --exclude '/launch.log' $C/ $R/ || exit 4
for i in 1 2 3 4; do for s in finished snapshot started status-after; do [[ -e $R/c3-w$i.$s ]] && mv $R/c3-w$i.$s $R/c9-w$i.$s; done; done
echo "imported 4 workers; results mirrored to $R ($(ls $R | wc -l | tr -d ' ') entries); records: $(ls $W/closure-evidence/v2/v2.1/mutation-workers/c9-w* | wc -l | tr -d ' ') files"
