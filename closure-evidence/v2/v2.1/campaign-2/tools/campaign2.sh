#!/bin/zsh
# campaign2.sh C SNAP NWORKERS [TABLE]: campaign 2 under the heavy lock (call it through heavy.sh). $C/queue.txt must
# exist (make_queue.py). Refuses below 15 GiB free; logs free space every 60 s; NWORKERS qworker.sh lanes pull from
# the queue; the operator's real OpenCode store is stat'ed before and after.
SP=/private/tmp/claude-501/-Users-nghinh-Downloads-projects-ai-sdlc/845c9f11-719f-4f92-a0ed-4f4a07d6e27b/scratchpad
C=$1; SNAP=$2; NW=$3; TABLE=$4
[[ -s $C/queue.txt && -n $SNAP && $NW -ge 1 ]] || { echo "usage: campaign2.sh C SNAP NWORKERS [TABLE]"; exit 2; }
free_gib() { df -g /System/Volumes/Data | awk 'NR==2{print $4}'; }
(( $(free_gib) >= 15 )) || { echo "REFUSED: $(free_gib) GiB free, 15 needed"; exit 4; }
( while [[ ! -e $C/campaign.done ]]; do echo "$(date '+%FT%T') $(free_gib) GiB free" >> $C/disk.log; sleep 60; done ) &
/opt/homebrew/bin/python3 $SP/s5/store_stat.py /Users/nghinh > $C/store-before.json
date -u +%FT%TZ > $C/campaign.started
ws=()
for i in $(seq 1 $NW); do zsh $C/qworker.sh $C c2-w$i $SNAP $TABLE & ws+=($!); sleep 5; done
wait $ws
/opt/homebrew/bin/python3 $SP/s5/store_stat.py /Users/nghinh > $C/store-after.json
date -u +%FT%TZ > $C/campaign.finished
echo done > $C/campaign.done
