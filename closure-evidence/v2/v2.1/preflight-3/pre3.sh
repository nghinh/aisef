#!/bin/zsh
# pre3: the T0 sweep (every distinct (null mutant, kill file) pair of the V2.1 targets, through the runner's own T0)
# at the campaign-2 commit 70423f9, a detached checkout, under the workers' env (env -i, PATH without opencode,
# scratch HOME/XDG/TMPDIR). The runner tests ran in the full suite at e6b06eb; campaign 1's runner-1 preflight is
# obsolete (runner v2 §5). Results outside the measured tree.
M=/private/tmp/claude-501/-Users-nghinh-Downloads-projects-ai-sdlc/845c9f11-719f-4f92-a0ed-4f4a07d6e27b/scratchpad/m21
S=$M/snap-70423f9; E=$M/pre3.env
GP=$(cat /private/tmp/claude-501/-Users-nghinh-Downloads-projects-ai-sdlc/845c9f11-719f-4f92-a0ed-4f4a07d6e27b/scratchpad/b03/l3c/gp.txt)
mkdir -p $E/home $E/xdg/{config,data,state,cache} $E/tmp
P() { env -i PATH=$GP HOME=$E/home XDG_CONFIG_HOME=$E/xdg/config XDG_DATA_HOME=$E/xdg/data XDG_STATE_HOME=$E/xdg/state \
      XDG_CACHE_HOME=$E/xdg/cache TMPDIR=$E/tmp LANG=en_US.UTF-8 USER=nghinh LOGNAME=nghinh /opt/homebrew/bin/python3 "$@"; }
cd $S || exit 9
echo "HEAD $(git rev-parse HEAD) dirty: [$(git status --porcelain | tr '\n' ' ')] free $(df -g /System/Volumes/Data | awk 'NR==2{print $4}') GiB"
echo "=== sweep $(date '+%F %T')"
P -P $M/sweep.py $M/pre3-sweep.jsonl > $M/pre3-sweep.log 2>&1; echo "sweep RC $?"
echo "HEAD after $(git rev-parse HEAD) dirty: [$(git status --porcelain | tr '\n' ' ')] free $(df -g /System/Volumes/Data | awk 'NR==2{print $4}') GiB"
echo "=== DONE $(date '+%F %T')"
