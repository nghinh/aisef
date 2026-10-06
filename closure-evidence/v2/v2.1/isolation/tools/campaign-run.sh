#!/bin/zsh
# campaign-run.sh TAG SNAP NAME...: called by campaign.sh under the heavy lock
SP=/private/tmp/claude-501/-Users-nghinh-Downloads-projects-ai-sdlc/845c9f11-719f-4f92-a0ed-4f4a07d6e27b/scratchpad
D=$SP/m21; TAG=$1; SNAP=$2; shift 2
/opt/homebrew/bin/python3 $SP/s5/store_stat.py /Users/nghinh > $D/$TAG.store-before.json
for n in "$@"; do zsh $D/worker.sh $n $SNAP & done
wait
/opt/homebrew/bin/python3 $SP/s5/store_stat.py /Users/nghinh > $D/$TAG.store-after.json
echo done > $D/$TAG.done
