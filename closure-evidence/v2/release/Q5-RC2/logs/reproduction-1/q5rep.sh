#!/bin/zsh
# RC2 S5 Q5 reproduction: validation/qualification/q5_run.sh in the fresh clone at fc519d3, attempt 1, hermetic
SP=/private/tmp/claude-501/-Users-nghinh-Downloads-projects-ai-sdlc/845c9f11-719f-4f92-a0ed-4f4a07d6e27b/scratchpad
R=$SP/s6rel; O=$SP/s6/q5
source $O/env.sh
date -u +%FT%TZ > $O/reproduce.started
zsh $SP/heavy.sh "RC2 Q5 reproduce" ${HENV[@]} /bin/zsh $R/validation/qualification/q5_run.sh > $O/q5_run.txt 2>&1
echo "exit $?" >> $O/q5_run.txt
date -u +%FT%TZ > $O/reproduce.finished
git -C $R status --porcelain > $O/status-after-reproduce.txt
echo done > $O/reproduce.done
