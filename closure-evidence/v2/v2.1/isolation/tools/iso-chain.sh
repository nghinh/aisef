#!/bin/zsh
# isolation proof (owner B-03b): the same 7 sample targets at 880881f, first by one worker alone, then by four at once
SP=/private/tmp/claude-501/-Users-nghinh-Downloads-projects-ai-sdlc/845c9f11-719f-4f92-a0ed-4f4a07d6e27b/scratchpad; D=$SP/m21
TAG=iso-alone zsh $D/campaign.sh 880881f iso-A
TAG=iso-concurrent zsh $D/campaign.sh 880881f iso-B iso-C iso-D iso-E
/opt/homebrew/bin/python3 -P $D/isolation_compare.py $D/ISOLATION-880881f.json iso-A iso-B iso-C iso-D iso-E > $D/iso-compare.out 2>&1
echo done > $D/iso-chain.done
