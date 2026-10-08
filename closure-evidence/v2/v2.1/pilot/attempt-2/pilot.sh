#!/bin/zsh
# pilot.sh SNAP TABLE: four lanes in parallel; lane i runs its targets twice in two fresh worktrees, in both orders —
# lanes 1 and 3 declared first, lanes 2 and 4 table order first, so neither order always runs on the warmer machine.
# Called under heavy.sh (no other heavy job overlaps).
SP=/private/tmp/claude-501/-Users-nghinh-Downloads-projects-ai-sdlc/845c9f11-719f-4f92-a0ed-4f4a07d6e27b/scratchpad
P=$SP/m21/pilot; SNAP=$1; TABLE=$2
# disk guard (attempt 1 hit ENOSPC at 2 GiB free): refuse below 15 GiB; log free space every 60 s while running
free_gib() { df -g /System/Volumes/Data | awk 'NR==2{print $4}'; }
(( $(free_gib) >= 15 )) || { echo "REFUSED: $(free_gib) GiB free, 15 needed"; exit 4; }
( while [[ ! -e $P/pilot.done ]]; do echo "$(date '+%FT%T') $(free_gib) GiB free" >> $P/disk.log; sleep 60; done ) &
/opt/homebrew/bin/python3 $SP/s5/store_stat.py /Users/nghinh > $P/store-before.json
lane() { local i=$1 first=$2 second=$3
  cp $P/lane$i.targets $P/l$i-$first.targets; cp $P/lane$i.targets $P/l$i-$second.targets
  zsh $P/pworker.sh l$i-$first $SNAP $first $TABLE; zsh $P/pworker.sh l$i-$second $SNAP $second $TABLE; }
lanes=()
lane 1 decl ord & lanes+=($!); lane 2 ord decl & lanes+=($!); lane 3 decl ord & lanes+=($!); lane 4 ord decl & lanes+=($!)
wait $lanes   # the lanes only: the disk monitor ends when pilot.done exists
/opt/homebrew/bin/python3 $SP/s5/store_stat.py /Users/nghinh > $P/store-after.json
echo done > $P/pilot.done
