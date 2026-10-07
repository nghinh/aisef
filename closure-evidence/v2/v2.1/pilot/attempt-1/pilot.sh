#!/bin/zsh
# pilot.sh SNAP TABLE: four lanes in parallel; lane i runs its targets twice in two fresh worktrees, in both orders —
# lanes 1 and 3 declared first, lanes 2 and 4 table order first, so neither order always runs on the warmer machine.
# Called under heavy.sh (no other heavy job overlaps).
SP=/private/tmp/claude-501/-Users-nghinh-Downloads-projects-ai-sdlc/845c9f11-719f-4f92-a0ed-4f4a07d6e27b/scratchpad
P=$SP/m21/pilot; SNAP=$1; TABLE=$2
/opt/homebrew/bin/python3 $SP/s5/store_stat.py /Users/nghinh > $P/store-before.json
lane() { local i=$1 first=$2 second=$3
  cp $P/lane$i.targets $P/l$i-$first.targets; cp $P/lane$i.targets $P/l$i-$second.targets
  zsh $P/pworker.sh l$i-$first $SNAP $first $TABLE; zsh $P/pworker.sh l$i-$second $SNAP $second $TABLE; }
lane 1 decl ord & lane 2 ord decl & lane 3 decl ord & lane 4 ord decl &
wait
/opt/homebrew/bin/python3 $SP/s5/store_stat.py /Users/nghinh > $P/store-after.json
echo done > $P/pilot.done
