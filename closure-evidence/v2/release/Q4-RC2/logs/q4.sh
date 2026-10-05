#!/bin/zsh
# RC2 S5 Q4: calibration, then the fresh 100,000-trace differential, release mode, hermetic, in the fresh clone
SP=/private/tmp/claude-501/-Users-nghinh-Downloads-projects-ai-sdlc/845c9f11-719f-4f92-a0ed-4f4a07d6e27b/scratchpad
R=$SP/s6rel; O=$SP/s6/q4
mkdir -p $O/home $O/xdg/config $O/xdg/data $O/xdg/state $O/xdg/cache $O/scratch
GUARD_PATH=$(print -rl -- ${(s.:.)PATH} | while read -r d; do [[ -x $d/opencode ]] || print -r -- $d; done | paste -sd: -)
HENV=(env -i PATH=$GUARD_PATH HOME=$O/home XDG_CONFIG_HOME=$O/xdg/config XDG_DATA_HOME=$O/xdg/data XDG_STATE_HOME=$O/xdg/state
      XDG_CACHE_HOME=$O/xdg/cache TMPDIR=/var/folders/y9/frkyw6m14_q020cmyzsh16jm0000gn/T/ LANG=en_US.UTF-8 USER=$USER LOGNAME=$LOGNAME AISEF_SCRATCH=$O/scratch)
print -r -- "HENV=(${(q)HENV[@]})" > $O/env.sh
cd $R || exit 2
date -u +%FT%TZ > $O/started
zsh $SP/heavy.sh "RC2 Q4 calibrate" $HENV /opt/homebrew/bin/python3 -P validation/qualification/q4_aggregate.py --calibrate > $O/calibrate.txt 2>&1; echo "exit $?" >> $O/calibrate.txt
zsh $SP/heavy.sh "RC2 Q4 100k (5 workers)" $HENV /bin/zsh validation/qualification/q4_run.sh 5 > $O/run.txt 2>&1; echo "exit $?" >> $O/run.txt
date -u +%FT%TZ > $O/finished
git status --porcelain > $O/status-after.txt
echo done > $O/done
