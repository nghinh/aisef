#!/bin/zsh
# campaign.sh SNAP NAME...: the workers NAME... at SNAP concurrently, holding the machine-wide heavy lock for the whole
# campaign (never the full suite and a mutation run at once); the operator's real OpenCode store stat'ed before and after.
# (launch 1 failed harmlessly: a `zsh -c` function did not see $D/$SP; kept in failed-launch-1/)
SP=/private/tmp/claude-501/-Users-nghinh-Downloads-projects-ai-sdlc/845c9f11-719f-4f92-a0ed-4f4a07d6e27b/scratchpad
D=$SP/m21; SNAP=$1; shift; TAG=${TAG:-campaign-$(date +%s)}
[[ -x $SP/heavy.sh && -f $D/worker.sh && -f $SP/s5/store_stat.py ]] || { echo "a helper is missing"; exit 2; }
zsh $SP/heavy.sh "m21 $TAG" zsh $D/campaign-run.sh $TAG $SNAP "$@"
