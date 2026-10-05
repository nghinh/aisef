#!/bin/zsh
# RC2 S5 Q0-Q3 local dry run (release mode, hermetic; a non-gate darwin observation before the [qualify] CI attempt)
SP=/private/tmp/claude-501/-Users-nghinh-Downloads-projects-ai-sdlc/845c9f11-719f-4f92-a0ed-4f4a07d6e27b/scratchpad
W=/Users/nghinh/Downloads/projects/ai-sdlc/.claude/worktrees/c2-corrective
SHA=$1; OUT=$2
[[ -n $SHA && -n $OUT && ! -e $OUT ]] || { echo "usage: dryrun-q.sh SHA OUT (OUT absent)"; exit 2; }
mkdir -p $OUT/home $OUT/xdg/config $OUT/xdg/data $OUT/xdg/state $OUT/xdg/cache
GUARD_PATH=$(print -rl -- ${(s.:.)PATH} | while read -r d; do [[ -x $d/opencode ]] || print -r -- $d; done | paste -sd: -)
HENV=(env -i PATH=$GUARD_PATH HOME=$OUT/home XDG_CONFIG_HOME=$OUT/xdg/config XDG_DATA_HOME=$OUT/xdg/data
      XDG_STATE_HOME=$OUT/xdg/state XDG_CACHE_HOME=$OUT/xdg/cache TMPDIR=/var/folders/y9/frkyw6m14_q020cmyzsh16jm0000gn/T/ LANG=en_US.UTF-8 USER=$USER LOGNAME=$LOGNAME)
print -r -- "HENV=(${(q)HENV[@]})" > $OUT/env.sh
git -C $W worktree add -q --detach $OUT/wt $SHA || exit 1
date -u +%FT%TZ > $OUT/started
(cd $OUT/wt && zsh $SP/heavy.sh "RC2 Q0-Q3 dry run $SHA" $HENV /opt/homebrew/bin/python3 -P validation/v2/owned_run.py --out $OUT/owned.json -- \
   /opt/homebrew/bin/python3 -P validation/qualification/run.py --rungs q0 q1 q2 q3 > $OUT/run.txt 2>&1; echo "exit $?" >> $OUT/run.txt)
date -u +%FT%TZ > $OUT/finished
git -C $OUT/wt status --porcelain > $OUT/status-after.txt
echo done > $OUT/done
