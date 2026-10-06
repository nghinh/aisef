#!/bin/zsh
# isolation proof, round 2 (round 1 at 880881f FAILED: one baseline of the claim-race test under load; fixed in 7fe1062)
zsh /private/tmp/claude-501/-Users-nghinh-Downloads-projects-ai-sdlc/845c9f11-719f-4f92-a0ed-4f4a07d6e27b/scratchpad/heavy.sh "m21 pre-cc53596" zsh /private/tmp/claude-501/-Users-nghinh-Downloads-projects-ai-sdlc/845c9f11-719f-4f92-a0ed-4f4a07d6e27b/scratchpad/m21/pre-cc53596.sh
TAG=iso2-alone zsh /private/tmp/claude-501/-Users-nghinh-Downloads-projects-ai-sdlc/845c9f11-719f-4f92-a0ed-4f4a07d6e27b/scratchpad/m21/campaign.sh cc53596 iso2-A
TAG=iso2-concurrent zsh /private/tmp/claude-501/-Users-nghinh-Downloads-projects-ai-sdlc/845c9f11-719f-4f92-a0ed-4f4a07d6e27b/scratchpad/m21/campaign.sh cc53596 iso2-B iso2-C iso2-D iso2-E
/opt/homebrew/bin/python3 -P /private/tmp/claude-501/-Users-nghinh-Downloads-projects-ai-sdlc/845c9f11-719f-4f92-a0ed-4f4a07d6e27b/scratchpad/m21/isolation_compare.py /private/tmp/claude-501/-Users-nghinh-Downloads-projects-ai-sdlc/845c9f11-719f-4f92-a0ed-4f4a07d6e27b/scratchpad/m21/ISOLATION-cc53596.json iso2-A iso2-B iso2-C iso2-D iso2-E > /private/tmp/claude-501/-Users-nghinh-Downloads-projects-ai-sdlc/845c9f11-719f-4f92-a0ed-4f4a07d6e27b/scratchpad/m21/iso2-compare.out 2>&1
echo done > /private/tmp/claude-501/-Users-nghinh-Downloads-projects-ai-sdlc/845c9f11-719f-4f92-a0ed-4f4a07d6e27b/scratchpad/m21/iso2-chain.done
