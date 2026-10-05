#!/bin/zsh
# RC2 S5 Q5: the corpus recorded once and the calibration, release mode, hermetic, in the fresh clone (scripted model stream)
SP=/private/tmp/claude-501/-Users-nghinh-Downloads-projects-ai-sdlc/845c9f11-719f-4f92-a0ed-4f4a07d6e27b/scratchpad
R=$SP/s6rel; O=$SP/s6/q5
mkdir -p $O/home $O/xdg/config $O/xdg/data $O/xdg/state $O/xdg/cache $O/scratch
GUARD_PATH=$(print -rl -- ${(s.:.)PATH} | while read -r d; do [[ -x $d/opencode ]] || print -r -- $d; done | paste -sd: -)
HENV=(env -i PATH=$GUARD_PATH HOME=$O/home XDG_CONFIG_HOME=$O/xdg/config XDG_DATA_HOME=$O/xdg/data XDG_STATE_HOME=$O/xdg/state
      XDG_CACHE_HOME=$O/xdg/cache TMPDIR=/var/folders/y9/frkyw6m14_q020cmyzsh16jm0000gn/T/ LANG=en_US.UTF-8 USER=$USER LOGNAME=$LOGNAME AISEF_SCRATCH=$O/scratch)
print -r -- "HENV=(${(q)HENV[@]})" > $O/env.sh
cd $R || exit 2
date -u +%FT%TZ > $O/record.started
zsh $SP/heavy.sh "RC2 Q5 record" $HENV /opt/homebrew/bin/python3 -P validation/v2/owned_run.py --out $O/owned-record.json -- /opt/homebrew/bin/python3 -P validation/qualification/q5.py --record > $O/record.txt 2>&1; echo "exit $?" >> $O/record.txt
zsh $SP/heavy.sh "RC2 Q5 calibrate" $HENV /opt/homebrew/bin/python3 -P validation/v2/owned_run.py --out $O/owned-calibrate.json -- /opt/homebrew/bin/python3 -P validation/qualification/q5.py --calibrate > $O/calibrate.txt 2>&1; echo "exit $?" >> $O/calibrate.txt
date -u +%FT%TZ > $O/record.finished
git status --porcelain > $O/status-after-record.txt
echo done > $O/record.done
