#!/bin/zsh
# run-suite.sh SHA OUT LABEL: the complete local suite on exactly SHA, in a fresh detached worktree OUT/rc, hermetic
# (env -i; fresh HOME and XDG_* under OUT; PATH without any directory holding an `opencode` executable), under the
# machine-wide heavy lock; before/after proofs of the hermetic roots and of the operator's real OpenCode store (os.stat).
SP=/private/tmp/claude-501/-Users-nghinh-Downloads-projects-ai-sdlc/845c9f11-719f-4f92-a0ed-4f4a07d6e27b/scratchpad
W=/Users/nghinh/Downloads/projects/ai-sdlc/.claude/worktrees/c2-corrective
SHA=$1; OUT=$2; LABEL=$3
[[ -n $SHA && -n $OUT && -n $LABEL && ! -e $OUT ]] || { echo "usage: run-suite.sh SHA OUT LABEL (OUT absent)"; exit 2; }
mkdir -p $OUT/home $OUT/xdg/config $OUT/xdg/data $OUT/xdg/state $OUT/xdg/cache
GUARD_PATH=$(print -rl -- ${(s.:.)PATH} | while read -r d; do [[ -x $d/opencode ]] || print -r -- $d; done | paste -sd: -)
HENV=(env -i PATH=$GUARD_PATH HOME=$OUT/home XDG_CONFIG_HOME=$OUT/xdg/config XDG_DATA_HOME=$OUT/xdg/data
      XDG_STATE_HOME=$OUT/xdg/state XDG_CACHE_HOME=$OUT/xdg/cache TMPDIR=/var/folders/y9/frkyw6m14_q020cmyzsh16jm0000gn/T/ LANG=en_US.UTF-8 USER=$USER LOGNAME=$LOGNAME)
print -r -- "HENV=(${(q)HENV[@]})" > $OUT/env.sh
git -C $W worktree add -q --detach $OUT/rc $SHA || exit 1
git -C $OUT/rc rev-parse HEAD > $OUT/rc-head-before.txt
(cd $OUT/rc && $HENV /opt/homebrew/bin/python3 $SP/s5/hermetic_proof.py) > $OUT/hermetic-proof-before.json 2>&1
/opt/homebrew/bin/python3 $SP/s5/store_stat.py /Users/nghinh > $OUT/real-store-before.json
date -u +%FT%TZ > $OUT/suite.started
(cd $OUT/rc && zsh $SP/heavy.sh "$LABEL" $HENV /opt/homebrew/bin/python3 -P validation/v2/owned_run.py --out $OUT/owned.json -- \
   /opt/homebrew/bin/python3 -m unittest discover -s tests > $OUT/suite.txt 2>&1; echo "exit $?" >> $OUT/suite.txt)
date -u +%FT%TZ > $OUT/suite.finished
git -C $OUT/rc status --porcelain > $OUT/rc-status-after.txt
git -C $OUT/rc rev-parse HEAD > $OUT/rc-head-after.txt
(cd $OUT/rc && $HENV /opt/homebrew/bin/python3 $SP/s5/hermetic_proof.py) > $OUT/hermetic-proof-after.json 2>&1
/opt/homebrew/bin/python3 $SP/s5/store_stat.py /Users/nghinh > $OUT/real-store-after.json
echo done > $OUT/suite.done
