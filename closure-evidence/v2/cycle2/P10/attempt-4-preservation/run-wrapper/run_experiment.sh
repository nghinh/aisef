#!/bin/zsh
# THE ONE PAID RUN (owner ruling 'OWNER AUTHORIZATION: DELIVERY EXPERIMENT ATTEMPT 4'): attempt 4, once. Detached from the
# session; the machine is kept awake for its duration. Nothing here retries anything.
SP=/private/tmp/claude-501/-Users-nghinh-Downloads-projects-ai-sdlc/845c9f11-719f-4f92-a0ed-4f4a07d6e27b/scratchpad
W=/Users/nghinh/Downloads/projects/ai-sdlc/.claude/worktrees/c2-corrective
cd $W || exit 9
test ! -e $SP/a4/run.started || { echo "REFUSED: this script already ran once" >> $SP/a4/run.log; exit 8; }
git rev-parse HEAD > $SP/a4/run.head
date '+%F %T' > $SP/a4/run.started
ATTEMPT=4 PROFILE=delivery-experiment-1 caffeinate -i zsh $SP/heavy.sh "DELIVERY-EXPERIMENT-1, attempt 4 (the one authorized run)" \
  validation/qualification/c2_p9_run.sh > $SP/a4/run.log 2>&1
echo "run script exit=$?" >> $SP/a4/run.log
date '+%F %T' > $SP/a4/run.finished
