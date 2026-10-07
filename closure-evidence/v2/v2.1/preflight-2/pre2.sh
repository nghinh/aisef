#!/bin/zsh
# pre2: at the campaign-2 snapshot 7577e16 (a detached checkout): the runner tests, the preflight (every distinct kill
# file on the unmutated tree) and the T0 sweep (every distinct (null mutant, kill file) pair), serially, under the
# workers' env (env -i, PATH without opencode, scratch HOME/XDG/TMPDIR). Results outside the measured tree.
M=/private/tmp/claude-501/-Users-nghinh-Downloads-projects-ai-sdlc/845c9f11-719f-4f92-a0ed-4f4a07d6e27b/scratchpad/m21
S=$M/snap-7577e16; E=$M/pre2.env
GP=$(cat /private/tmp/claude-501/-Users-nghinh-Downloads-projects-ai-sdlc/845c9f11-719f-4f92-a0ed-4f4a07d6e27b/scratchpad/b03/l3c/gp.txt)
mkdir -p $E/home $E/xdg/{config,data,state,cache} $E/tmp
P() { env -i PATH=$GP HOME=$E/home XDG_CONFIG_HOME=$E/xdg/config XDG_DATA_HOME=$E/xdg/data XDG_STATE_HOME=$E/xdg/state \
      XDG_CACHE_HOME=$E/xdg/cache TMPDIR=$E/tmp LANG=en_US.UTF-8 USER=nghinh LOGNAME=nghinh /opt/homebrew/bin/python3 "$@"; }
cd $S || exit 9
echo "HEAD $(git rev-parse HEAD) dirty: [$(git status --porcelain | tr '\n' ' ')]"
echo "=== runner tests $(date '+%F %T')"
P -B -m unittest tests.v2.test_v21_mutation_runner tests.v2.test_v21_execution_order > $M/pre2-runner.log 2>&1; echo "runner tests RC $? : $(tail -1 $M/pre2-runner.log)"
echo "=== preflight $(date '+%F %T')"
P -P $M/preflight.py $S $M/pre2-preflight.json V2.1 > $M/pre2-preflight.log 2>&1; echo "preflight RC $?"
echo "=== sweep $(date '+%F %T')"
P -P $M/sweep.py $M/pre2-sweep.jsonl > $M/pre2-sweep.log 2>&1; echo "sweep RC $?"
echo "HEAD after $(git rev-parse HEAD) dirty: [$(git status --porcelain | tr '\n' ' ')]"
echo "=== DONE $(date '+%F %T')"
