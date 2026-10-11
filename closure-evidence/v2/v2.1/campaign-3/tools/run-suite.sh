#!/bin/zsh
# run-suite.sh SHA OUT LABEL: the complete local suite on exactly SHA, in a fresh detached worktree OUT/rc, hermetic
# (env -i; fresh HOME, XDG_* and TMPDIR under OUT; PATH without any directory holding an `opencode` executable), under the
# machine-wide heavy lock; before/after proofs of the hermetic roots and of the operator's real OpenCode store (os.stat).
# Seeded from closure-evidence/v2/release/s5-rc2/run-suite.sh; the two helpers are the repository's own copies.
SP=/private/tmp/claude-501/-Users-nghinh-Downloads-projects-ai-sdlc/845c9f11-719f-4f92-a0ed-4f4a07d6e27b/scratchpad
W=/Users/nghinh/Downloads/projects/ai-sdlc/.claude/worktrees/v21
HP=$W/closure-evidence/v2/release/s5-rc2/hermetic_proof.py
SS=$W/closure-evidence/v2/v2.1/isolation/tools/store_stat.py
SHA=$1; OUT=$2; LABEL=$3
[[ -n $SHA && -n $OUT && -n $LABEL && ! -e $OUT ]] || { echo "usage: run-suite.sh SHA OUT LABEL (OUT absent)"; exit 2; }
mkdir -p $OUT/home $OUT/xdg/config $OUT/xdg/data $OUT/xdg/state $OUT/xdg/cache $OUT/tmp
GUARD_PATH=$(print -rl -- ${(s.:.)PATH} | while read -r d; do [[ -x $d/opencode ]] || print -r -- $d; done | paste -sd: -)
HENV=(env -i PATH=$GUARD_PATH HOME=$OUT/home XDG_CONFIG_HOME=$OUT/xdg/config XDG_DATA_HOME=$OUT/xdg/data
      XDG_STATE_HOME=$OUT/xdg/state XDG_CACHE_HOME=$OUT/xdg/cache TMPDIR=$OUT/tmp LANG=en_US.UTF-8 USER=$USER LOGNAME=$LOGNAME)
print -r -- "HENV=(${(q)HENV[@]})" > $OUT/env.sh
git -C $W worktree add -q --detach $OUT/rc $SHA || exit 1
git -C $OUT/rc rev-parse HEAD > $OUT/rc-head-before.txt
(cd $OUT/rc && $HENV /opt/homebrew/bin/python3 $HP) > $OUT/hermetic-proof-before.json 2>&1
/opt/homebrew/bin/python3 $SS /Users/nghinh > $OUT/real-store-before.json
date -u +%FT%TZ > $OUT/suite.started
(cd $OUT/rc && zsh $SP/heavy.sh "$LABEL" $HENV /opt/homebrew/bin/python3 -P validation/v2/owned_run.py --out $OUT/owned.json -- \
   /opt/homebrew/bin/python3 -m unittest discover -v -s tests > $OUT/suite.txt 2>&1; echo "exit $?" >> $OUT/suite.txt)
date -u +%FT%TZ > $OUT/suite.finished
git -C $OUT/rc status --porcelain > $OUT/rc-status-after.txt
git -C $OUT/rc rev-parse HEAD > $OUT/rc-head-after.txt
(cd $OUT/rc && $HENV /opt/homebrew/bin/python3 $HP) > $OUT/hermetic-proof-after.json 2>&1
/opt/homebrew/bin/python3 $SS /Users/nghinh > $OUT/real-store-after.json
echo done > $OUT/suite.done
